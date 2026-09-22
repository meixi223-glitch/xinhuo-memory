"""Translate authoritative SQLite rows to the observation-room domain model."""
import json
from datetime import datetime, timedelta, timezone
from memory_v2 import SECRET

COLORS = ['#bd7054','#6b83a0','#9380a6','#ad6575','#538a89','#87916b','#ad8735','#6c8e71']


def iso(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value or '')


def channel(source):
    s = str(source or '').lower()
    if 'wecom' in s or s == '企微': return '企微'
    if 'forum' in s or s == '论坛': return '论坛'
    if s in ('chat', 'conversation', 'room', '聊天'): return '聊天'
    return '其他'


def entry(m):
    return {'id': m['id'], 'title': (m.get('summary') or m['content'])[:80], 'body': m['content'], 'at': iso(m.get('occurred_at')), 'channels': [channel(m.get('source'))], 'kind': 'memory', 'tags': m.get('tags', []), 'emotion': m.get('emotion_label'), 'versionStatus': m.get('version_status'), 'pinned': bool(m.get('pinned')), 'layer': m.get('layer', 'episodic')}


def entries(store, offset=0, query=''):
    # Stable combined pagination. Source identity, not similar text, drives UI merging.
    with store.connect() as db:
        rows = db.execute("""SELECT id,occurred_at at,'memory' kind FROM memories WHERE namespace='default' AND version_status='current' AND (content LIKE ? OR summary LIKE ?)
            UNION ALL SELECT event_id id,occurred_at_utc at,'event' kind FROM events WHERE namespace='default' AND content LIKE ?
            ORDER BY at DESC,id DESC LIMIT 101 OFFSET ?""", ('%'+query+'%', '%'+query+'%', '%'+query+'%', offset)).fetchall()
        result = []
        for row in rows[:100]:
            if row['kind'] == 'memory':
                item = entry(store.get(row['id']))
            else:
                e = dict(db.execute('SELECT * FROM events WHERE event_id=?', (row['id'],)).fetchone())
                if SECRET.search(e['content']): continue
                item = {'id': e['event_id'], 'title': e['content'][:80], 'body': e['content'], 'at': e['occurred_at_utc'], 'channels': [channel(e['channel'])], 'kind': 'event', 'canonicalId': e['source_raw_event_id'] or e['event_id'], 'tags': [e['role'], e['privacy_label']]}
            result.append(item)
    return {'items': result, 'nextOffset': offset+100 if len(rows)>100 else None}


def snapshot(store, frames):
    overview = store.overview()
    mood = store.affect.snapshot()
    coords = store.affect.coordinates()
    reports = store.affect.why(limit=100)['items']
    latest = reports[0] if reports else None
    frame = frames.latest()
    daily = store.daily.browse(100)['items']
    recalls = store.recalls(limit=100)['items']
    page = entries(store)
    with store.connect() as db:
        recall_count = db.execute("SELECT count(*) FROM recall_log WHERE namespace='default'").fetchone()[0]
        daily_count = db.execute("SELECT count(*) FROM daily_impressions WHERE namespace='default'").fetchone()[0]
    jobs = overview['progress']['jobs']
    now = datetime.now(timezone.utc)
    mapped_recalls = []
    for r in recalls:
        selected = r['selected']
        if isinstance(selected, dict): selected = selected.get('items', [])
        items = []
        for selected_item in selected:
            if isinstance(selected_item,dict) and selected_item.get('returned') is False: continue
            mid = selected_item if isinstance(selected_item, str) else selected_item.get('id', '')
            m = store.get(mid)
            items.append({'id': mid, 'title': (m.get('summary') or m['content'])[:100] if m else mid, 'reason': selected_item.get('reason', r.get('reason') or '') if isinstance(selected_item, dict) else r.get('reason') or ''})
        mapped_recalls.append({'id': r['id'], 'at': r['created_at'], 'channel': '其他', 'query': r['query'] or '', 'items': items})
    return {
        'source': 'live', 'capturedAt': now.isoformat(), 'expiresAt': (now+timedelta(minutes=2)).isoformat(),
        'mood': {'v': coords['valence'] if mood['last_change'] else None, 'a': coords['arousal'] if mood['last_change'] else None, 'label': '、'.join(mood['labels']) if mood['last_change'] else '尚无自述', 'updatedAt': iso(mood['updated_at']), 'dimensions': {k: latest['dims'].get(k) if latest else None for k in mood['emotion_dimensions']}, 'note': '圆环显示衰减后的 Russell 坐标；配方显示最近自评的基础情绪变化量（-0.18～0.18），不是当前强度。', 'dimensionMode': 'delta'},
        'scene': {'focus': frame['focus'] if frame else '', 'phase': frame['phase'] if frame else '', 'body': frame['body_state'] if frame else '', 'transition': frame['transition'] if frame else '', 'expiresAt': (datetime.fromisoformat(frame['generated_at_utc'].replace('Z', '+00:00'))+timedelta(seconds=frame['ttl_seconds'])).isoformat() if frame else None},
        'entries': page['items'], 'nextOffset': page['nextOffset'],
        'reports': [{'id': r['id'], 'at': r['created_at'], 'v': r['valence'], 'a': r['arousal'], 'label': '、'.join(r['labels']), 'reason': r['reason'], 'quote': '\n'.join(r['evidence'])} for r in reports],
        'impressions': [{'day': r['day'], 'summary': r['summary'], 'theme': r['theme'], 'source': '每日印象工人'} for r in daily],
        'recalls': mapped_recalls, 'unknown': [],
        'stats': {'memories': sum(overview['counts'].values()), 'events': overview['events'], 'recalls': recall_count, 'impressions': daily_count, 'today': overview['today']['calls'], 'pending': jobs.get('queued', 0)+jobs.get('running', 0), 'done': jobs.get('done', 0), 'failed': jobs.get('failed', 0), 'projected': overview['vector_projection']['indexed'] if overview['vector_projection']['configured'] else overview['vectors'], 'projectionTotal': overview['progress']['indexable']},
        'wakePolicy': store.daily.wake_policy(),
        'relationships': mood['relationship_dimensions'],
    }


def emotion_config(store):
    from affect_core import BASIC_DIMS
    return {'dimensions': [{'id': k, 'name': v, 'color': color} for (k,v),color in zip(BASIC_DIMS.items(), COLORS)], 'quadrants': ['兴奋','紧张','低落','平静'], 'compositeRules': [], 'vaRules': [], 'fallbackLabel': '平静'}
