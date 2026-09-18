import importlib
import os
import tempfile
import unittest


class TestContinuityServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        os.environ["MEMORY_DB"]=cls.tmp.name+"/db"
        os.environ["MEMORY_ARCHIVE_DIR"]=cls.tmp.name+"/archive"
        import server
        cls.server=importlib.reload(server)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_tools_and_schemas_are_additive(self):
        names=[name for name,_ in self.server.TOOLS]
        for name in ("continuity_status","continuity_recall","continuity_trajectories","continuity_nearfield","continuity_latents"):
            self.assertIn(name,names);self.assertEqual(self.server.schema_for(name)["type"],"object")
        self.assertNotIn("continuity_latent_review",names);self.assertNotIn("continuity_trajectory_state",names)
        self.assertEqual(self.server.schema_for("memory_recall")["required"],["query"])

    def test_read_tools_start_empty_without_touching_memory(self):
        self.assertEqual(self.server.call_tool("continuity_status",{})["trajectory"]["total"],0)
        self.assertEqual(self.server.call_tool("continuity_recall",{"query":"test"})["items"],[])
        with self.server.STORE.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM continuity_recall_log").fetchone()[0],0)
        self.assertEqual(self.server.call_tool("memory_list",{}),[])


if __name__=="__main__":unittest.main()
