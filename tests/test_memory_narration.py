import unittest
from memory_narration import safe_style_edits

class NarrationEditsTest(unittest.TestCase):
    def test_owner_name_and_pronoun_only(self):
        edits=safe_style_edits('用户说他睡得很好。','阿岚说她睡得很好。')
        self.assertEqual([e['before'] for e in edits],['用户','他'])

    def test_quotes_preserved_while_narration_changes(self):
        before='用户说：“他是小星。”他的愿望是继续共读。'
        self.assertIsNotNone(safe_style_edits(before,'阿岚说：“他是小星。”她的愿望是继续共读。'))
        self.assertIsNone(safe_style_edits(before,'阿岚说：“她是小星。”她的愿望是继续共读。'))

    def test_verbatim_evidence_without_quote_marks_is_protected(self):
        self.assertIsNone(safe_style_edits('用户记录：他很好','阿岚记录：她很好',['他很好']))

    def test_technical_and_third_party_lexemes_preserved(self):
        for a,b in [('其他用户','其他阿岚'),('其他','其她'),('用户名','阿岚名'),('用户权限','阿岚权限'),('他们','她们'),('他人','她人'),('吉他','吉她')]:
            with self.subTest(a=a):self.assertIsNone(safe_style_edits(a,b))

    def test_facts_cannot_be_changed_in_same_pass(self):
        self.assertIsNone(safe_style_edits('用户说他没完成。','阿岚说她已完成。'))
        self.assertIsNone(safe_style_edits('用户喜欢猫','阿岚非常喜欢猫'))

    def test_no_change_is_valid_without_any_edits(self):
        self.assertEqual(safe_style_edits('小星说他愿意陪她。','小星说他愿意陪她。'),[])

if __name__=='__main__':unittest.main()
