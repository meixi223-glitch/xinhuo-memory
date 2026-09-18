"""Owner-authorized narration, separate from immutable source words and API roles."""
import re

NARRATION_VERSION = 'alan-she-v1'
NARRATION_RULES = '''称谓与人称口径（整理文字适用，原文证据不适用）：
在小星与阿岚的真实对话、default命名空间及owner_note中，user/owner本人是阿岚，女性。整理后的content、summary、实体名称中，指她本人统一写“阿岚”，后续自然用“她／她的”，不用“用户／该用户／他／他的”称呼阿岚。只调整叙述口径，不添加身份之外的新事实。
普通记忆区分“阿岚…”与“小星…”；若任务指定小星第一人称日记，“我”是小星，阿岚仍为“阿岚／她”，不能把阿岚的经历改成小星经历。
user、assistant、owner等JSON字段、角色标识、ID、fact_key保持协议原值。quote、书籍原文、引号里的逐字引用完全不改。小说角色、其他人及其他命名空间不能被替换成阿岚；指小星或其他男性的“他”保留。“其他、他人、他们、用户名、用户权限、操作系统用户”等一般概念不能机械替换。
核对时将“本次真实对话的用户”规范为“阿岚／她”视为已知称谓，不视为捏造，但必须拒绝错认第三方、改变性别指代、篡改引文或把阿岚仍叙述成“用户／他”的生成文字。'''

def narration(instruction):
    return instruction + '\n' + NARRATION_RULES

# Conservative guard used by the one-time, independently reviewed correction.
# Equal-length substitutions make every unchanged character easy to verify.
QUOTED = re.compile(r'“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|"[^"\n]*"|\x27[^\x27\n]*\x27|`[^`]*`')
TECHNICAL = re.compile(r'其他用户|普通用户|系统用户|多用户|所有用户|用户名|用户态|用户组|用户(?:ID|id|界面|数据|权限|目录|令牌|认证|管理|标识|文件)|其他|他人|他们|他乡|利他|吉他|他方|他处|无他')

def safe_style_edits(before, after, quotes=()):
    """Return changed spans, or None for non-style/quoted/technical changes.

    This does not infer referents: an independent model must also verify them.
    """
    if not isinstance(before,str) or not isinstance(after,str) or len(before)!=len(after):
        return None
    protected=set()
    for pattern in (QUOTED, TECHNICAL):
        for match in pattern.finditer(before):protected.update(range(match.start(),match.end()))
    for quote in quotes:
        if not isinstance(quote,str) or not quote:continue
        start=0
        while True:
            start=before.find(quote,start)
            if start<0:break
            protected.update(range(start,start+len(quote)));start+=len(quote)
    changes=[];i=0
    while i<len(before):
        if before[i]==after[i]:i+=1;continue
        n=2 if before[i:i+2]=='用户' and after[i:i+2]=='阿岚' else 1 if before[i]=='他' and after[i]=='她' else 0
        if not n or any(j in protected for j in range(i,i+n)):return None
        changes.append({'start':i,'before':before[i:i+n],'after':after[i:i+n]});i+=n
    return changes
