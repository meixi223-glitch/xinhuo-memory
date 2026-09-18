"""Optional Qdrant read index for memory vectors.

SQLite remains authoritative. Qdrant receives only vector and integrity/filter
metadata; no memory text, evidence, credentials, or instructions are stored in
the derived index. Callers must validate returned hashes against SQLite.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

POINT_NAMESPACE=uuid.UUID('42197fe2-7f42-4e58-8979-6f2b0766dd44')


class VectorIndexUnavailable(RuntimeError):
    pass


class QdrantVectorIndex:
    def __init__(self, url=None, collection=None, api_key=None, timeout=3):
        self.url=str(url if url is not None else os.getenv('MEMORY_VECTOR_URL','')).rstrip('/')
        self.collection=str(collection if collection is not None else os.getenv('MEMORY_VECTOR_COLLECTION','xinhuo_memories'))
        self.api_key=str(api_key if api_key is not None else os.getenv('MEMORY_VECTOR_API_KEY',''))
        self.timeout=float(timeout)

    @property
    def enabled(self):
        return bool(self.url)

    def _request(self,method,path,body=None,timeout=None):
        data=None if body is None else json.dumps(body,separators=(',',':')).encode()
        headers={'content-type':'application/json'}
        if self.api_key:headers['api-key']=self.api_key
        request=urllib.request.Request(self.url+path,data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(request,timeout=timeout or self.timeout) as response:
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise VectorIndexUnavailable('response_too_large')
                return json.loads(raw or b'{}')
        except urllib.error.HTTPError as exc:
            raise VectorIndexUnavailable('http_'+str(exc.code)) from None
        except (urllib.error.URLError,OSError,ValueError) as exc:
            raise VectorIndexUnavailable(type(exc).__name__) from None

    @staticmethod
    def point_id(memory_id):
        return str(uuid.uuid5(POINT_NAMESPACE,str(memory_id)))

    def ensure_collection(self,dimension):
        if not self.enabled:raise VectorIndexUnavailable('not_configured')
        name=urllib.parse.quote(self.collection,safe='')
        try:
            self._request('GET',f'/collections/{name}')
            return False
        except VectorIndexUnavailable as exc:
            if str(exc)!='http_404':raise
        self._request('PUT',f'/collections/{name}',{
            'vectors':{'size':int(dimension),'distance':'Cosine','on_disk':True},
            'hnsw_config':{'m':16,'ef_construct':128,'on_disk':True},
            'on_disk_payload':True,
        },timeout=30)
        for field in ('namespace','model','status'):
            self._request('PUT',f'/collections/{name}/index',{'field_name':field,'field_schema':'keyword'},timeout=30)
        return True

    def upsert(self,items):
        if not items:return 0
        name=urllib.parse.quote(self.collection,safe='')
        points=[]
        for item in items:
            mid=str(item['memory_id'])
            points.append({'id':self.point_id(mid),'vector':item['vector'],'payload':{
                'memory_id':mid,'content_hash':str(item['content_hash']),
                'namespace':str(item['namespace']),'model':str(item['model']),
                'status':str(item['status']),
            }})
        self._request('PUT',f'/collections/{name}/points?wait=true',{'points':points},timeout=60)
        return len(points)

    def delete(self,memory_ids):
        ids=[self.point_id(mid) for mid in memory_ids]
        if not ids:return 0
        name=urllib.parse.quote(self.collection,safe='')
        self._request('POST',f'/collections/{name}/points/delete?wait=true',{'points':ids},timeout=60)
        return len(ids)

    def search(self,vector,namespace,model,limit=40,score_threshold=.35):
        if not self.enabled:raise VectorIndexUnavailable('not_configured')
        name=urllib.parse.quote(self.collection,safe='')
        result=self._request('POST',f'/collections/{name}/points/query',{
            'query':vector,
            'filter':{'must':[
                {'key':'namespace','match':{'value':namespace}},
                {'key':'model','match':{'value':model}},
            ]},
            'limit':max(1,min(100,int(limit))),
            'score_threshold':float(score_threshold),
            'with_payload':['memory_id','content_hash','model','namespace'],
            'with_vector':False,
        })
        points=(result.get('result') or {}).get('points',[])
        hits={}
        for point in points:
            payload=point.get('payload') or {};mid=payload.get('memory_id')
            if not isinstance(mid,str) or not mid:continue
            if payload.get('namespace')!=namespace or payload.get('model')!=model:continue
            try:score=float(point.get('score'))
            except (TypeError,ValueError):continue
            hits[mid]={'score':score,'content_hash':str(payload.get('content_hash') or '')}
        return hits
