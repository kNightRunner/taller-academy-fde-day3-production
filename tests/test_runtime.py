"""Offline verification of provider compatibility (3 tests)."""
import unittest
from types import SimpleNamespace
from runtime import MessageAPI

class FakeBackend:
    def __init__(self):
        self.calls=[]
    def generate(self,messages,tools=None):
        self.calls.append((messages,tools))
        return SimpleNamespace(text="OK",tool_calls=[],input_tokens=12,output_tokens=3,model="fake")

class RuntimeTests(unittest.TestCase):
    def test_no_fake_exact_token_count(self):
        api=MessageAPI(FakeBackend())
        with self.assertRaises(RuntimeError):
            api.count_tokens(messages=[])

    def test_basic_model_response(self):
        backend=FakeBackend()
        response=MessageAPI(backend).create(model="test",max_tokens=50,messages=[{"role":"user","content":"hello"}])
        self.assertEqual(response.content[0].text,"OK")
        self.assertEqual(response.usage.input_tokens,12)
        self.assertEqual(response.usage.output_tokens,3)
        self.assertEqual(response.stop_reason,"end_turn")

    def test_tool_result_becomes_tool_message(self):
        backend=FakeBackend()
        api=MessageAPI(backend)
        messages=[
            {"role":"user","content":"run"},
            {"role":"assistant","content":[{"type":"tool_use","id":"t1","name":"search_documents","input":{"query":"budget"}}]},
            {"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"found"}]},
        ]
        api.create(model="test",max_tokens=100,messages=messages)
        observed=backend.calls[0][0]
        self.assertEqual(observed[-1]["role"],"tool")
        self.assertEqual(observed[-1]["tool_name"],"search_documents")
        self.assertEqual(observed[-1]["content"],"found")

if __name__=="__main__":
    unittest.main()
