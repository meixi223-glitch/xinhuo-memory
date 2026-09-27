import unittest
from memory_narration import safe_style_edits, OWNER_NAME, COMPANION_NAME, OWNER_PRONOUN, WRONG_PRONOUN

# Configuration-driven fixtures: the guard rewrites the generic "用户" into the
# configured owner name and the wrong-gender pronoun into the owner's pronoun.
OWNER, COMP, PRON, WRONG = OWNER_NAME, COMPANION_NAME, OWNER_PRONOUN, WRONG_PRONOUN


class NarrationEditsTest(unittest.TestCase):
    def test_owner_name_and_pronoun_only(self):
        edits=safe_style_edits(f'用户说{WRONG}睡得很好。',f'{OWNER}说{PRON}睡得很好。')
        self.assertEqual([e['before'] for e in edits],['用户',WRONG])

    def test_quotes_preserved_while_narration_changes(self):
        before=f'用户说：“{WRONG}是{COMP}。”{WRONG}的愿望是继续共读。'
        self.assertIsNotNone(safe_style_edits(before,f'{OWNER}说：“{WRONG}是{COMP}。”{PRON}的愿望是继续共读。'))
        self.assertIsNone(safe_style_edits(before,f'{OWNER}说：“{PRON}是{COMP}。”{PRON}的愿望是继续共读。'))

    def test_verbatim_evidence_without_quote_marks_is_protected(self):
        self.assertIsNone(safe_style_edits(f'用户记录：{WRONG}很好',f'{OWNER}记录：{PRON}很好',[f'{WRONG}很好']))

    def test_technical_and_third_party_lexemes_preserved(self):
        # "用户"-compound protection is language-fixed and config-independent.
        for a,b in [('其他用户','其他'+OWNER),('用户名',OWNER+'名'),('用户权限',OWNER+'权限')]:
            with self.subTest(a=a):self.assertIsNone(safe_style_edits(a,b))
        # The pronoun-idiom word list (其他/他们/他人/吉他) guards the generic "他";
        # it only applies when that is the wrong-pronoun being corrected away from.
        if WRONG=='他':
            for a,b in [('其他','其'+PRON),(WRONG+'们',PRON+'们'),(WRONG+'人',PRON+'人'),('吉'+WRONG,'吉'+PRON)]:
                with self.subTest(a=a):self.assertIsNone(safe_style_edits(a,b))

    def test_facts_cannot_be_changed_in_same_pass(self):
        self.assertIsNone(safe_style_edits(f'用户说{WRONG}没完成。',f'{OWNER}说{PRON}已完成。'))
        self.assertIsNone(safe_style_edits('用户喜欢猫',OWNER+'非常喜欢猫'))

    def test_no_change_is_valid_without_any_edits(self):
        text=f'{COMP}说{WRONG}愿意陪{PRON}。'
        self.assertEqual(safe_style_edits(text,text),[])

if __name__=='__main__':unittest.main()
