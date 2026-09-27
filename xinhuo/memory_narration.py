"""Owner-authorized narration, separate from immutable source words and API roles.

The owner/companion identity is configuration, not code. Each deployment sets who
its memory belongs to via .env (OWNER_NAME / COMPANION_NAME / OWNER_PRONOUN); the
narration rules and derived version string are rendered from that configuration so
one installation's owner name never leaks into another's memories.
"""
import os
import re


def _env(name, default):
    value = os.getenv(name, '')
    value = value.strip() if isinstance(value, str) else ''
    return value or default


# Deployment-configurable identity. Defaults are neutral placeholders.
OWNER_NAME = _env('OWNER_NAME', '主人')
COMPANION_NAME = _env('COMPANION_NAME', '小星')
OWNER_PRONOUN = _env('OWNER_PRONOUN', '她')
OWNER_POSSESSIVE = OWNER_PRONOUN + '的'
# The pronoun that must NOT be used for the owner (the other gendered third person).
WRONG_PRONOUN = {'她': '他', '他': '她'}.get(OWNER_PRONOUN, '他')
# Optional gender clause, only stated when the pronoun implies one.
_GENDER = {'她': '，女性', '他': '，男性'}.get(OWNER_PRONOUN, '')


def _rules():
    owner, companion, pron, poss = OWNER_NAME, COMPANION_NAME, OWNER_PRONOUN, OWNER_POSSESSIVE
    wrong = WRONG_PRONOUN
    return (
        '称谓与人称口径（整理文字适用，原文证据不适用）：\n'
        f'在{companion}与{owner}的真实对话、default命名空间及owner_note中，user/owner本人是{owner}{_GENDER}。'
        f'整理后的content、summary、实体名称中，指{pron}本人统一写“{owner}”，后续自然用“{pron}／{poss}”，'
        f'不用“用户／该用户／{wrong}／{wrong}的”称呼{owner}。只调整叙述口径，不添加身份之外的新事实。\n'
        f'普通记忆区分“{owner}…”与“{companion}…”；若任务指定{companion}第一人称日记，“我”是{companion}，'
        f'{owner}仍为“{owner}／{pron}”，不能把{owner}的经历改成{companion}经历。\n'
        'user、assistant、owner等JSON字段、角色标识、ID、fact_key保持协议原值。quote、书籍原文、引号里的逐字引用完全不改。'
        f'小说角色、其他人及其他命名空间不能被替换成{owner}；指{companion}或其他人的原有代词保留。'
        '“其他、他人、他们、用户名、用户权限、操作系统用户”等一般概念不能机械替换。\n'
        f'核对时将“本次真实对话的用户”规范为“{owner}／{pron}”视为已知称谓，不视为捏造，'
        f'但必须拒绝错认第三方、改变性别指代、篡改引文或把{owner}仍叙述成“用户／{wrong}”的生成文字。'
    )


NARRATION_RULES = _rules()
# Version encodes the identity so caches keyed on it invalidate when it changes.
NARRATION_VERSION = 'owner-{}-{}-v1'.format(OWNER_NAME, OWNER_PRONOUN)


def narration(instruction):
    return instruction + '\n' + NARRATION_RULES

# Conservative guard used by the one-time, independently reviewed correction.
# Equal-length substitutions make every unchanged character easy to verify.
QUOTED = re.compile(r'“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|"[^"\n]*"|\x27[^\x27\n]*\x27|`[^`]*`')
TECHNICAL = re.compile(r'其他用户|普通用户|系统用户|多用户|所有用户|用户名|用户态|用户组|用户(?:ID|id|界面|数据|权限|目录|令牌|认证|管理|标识|文件)|其他|他人|他们|他乡|利他|吉他|他方|他处|无他')

def safe_style_edits(before, after, quotes=()):
    """Return changed spans, or None for non-style/quoted/technical changes.

    This does not infer referents: an independent model must also verify them.
    Only two rewrites are allowed: the generic "用户" into the configured owner
    name (when that name is two characters) and the wrong-gender third-person
    pronoun into the owner's pronoun.
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
        n=2 if before[i:i+2]=='用户' and len(OWNER_NAME)==2 and after[i:i+2]==OWNER_NAME else 1 if before[i]==WRONG_PRONOUN and after[i]==OWNER_PRONOUN else 0
        if not n or any(j in protected for j in range(i,i+n)):return None
        changes.append({'start':i,'before':before[i:i+n],'after':after[i:i+n]});i+=n
    return changes
