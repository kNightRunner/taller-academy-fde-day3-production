"""Anthropic-style response compatibility layer backed by Ollama or Anthropic."""
from __future__ import annotations
import os
from types import SimpleNamespace
from src.production.providers import OllamaProvider, AnthropicProvider

PROVIDER=os.environ.get("FDE_PROVIDER","ollama").lower()
MODEL=os.environ.get("FDE_MODEL","qwen2.5:3b" if PROVIDER=="ollama" else "claude-sonnet-4-5")

class MessageAPI:
    def __init__(self, backend):
        self.backend=backend

    def create(self, *, model, max_tokens, messages, system="", tools=None,
               output_config=None, cache_control=None, **kwargs):
        if cache_control is not None and isinstance(self.backend,OllamaProvider):
            raise RuntimeError("Ollama does not implement Anthropic prompt caching.")
        converted=[]
        names={}
        if system:
            converted.append({"role":"system","content":system})
        for m in messages:
            role=m["role"]
            content=m.get("content","")
            if isinstance(content,str):
                converted.append({"role":role,"content":content})
                continue
            if role=="assistant":
                calls=[]
                texts=[]
                for b in content:
                    if isinstance(b,dict):
                        typ=b.get("type")
                        g=lambda k,default=None:b.get(k,default)
                    else:
                        typ=getattr(b,"type",None)
                        g=lambda k,default=None:getattr(b,k,default)
                    if typ=="tool_use":
                        calls.append({"id":g("id"),"name":g("name"),"arguments":g("input")})
                        names[g("id")]=g("name")
                    elif typ=="text":
                        texts.append(g("text",""))
                converted.append({"role":"assistant","content":"\n".join(texts),"tool_calls":calls})
            elif role=="user":
                for b in content:
                    if isinstance(b,dict) and b.get("type")=="tool_result":
                        converted.append({"role":"tool","tool_name":names.get(b.get("tool_use_id"),"unknown_tool"),
                                          "tool_call_id":b.get("tool_use_id"),"content":b.get("content",""),
                                          "is_error":b.get("is_error",False)})
                    elif isinstance(b,dict) and b.get("type")=="text":
                        converted.append({"role":"user","content":b["text"]})
                    else:
                        converted.append({"role":"user","content":str(b)})
            else:
                raise TypeError(f"Unsupported role: {role}")
        r=self.backend.generate(converted,tools=tools)
        blocks=[]
        if r.text:
            blocks.append(SimpleNamespace(type="text",text=r.text))
        for call in r.tool_calls:
            blocks.append(SimpleNamespace(type="tool_use",id=call.id,name=call.name,input=call.arguments))
        return SimpleNamespace(content=blocks,stop_reason="tool_use" if r.tool_calls else "end_turn",
                               usage=SimpleNamespace(input_tokens=r.input_tokens or 0,output_tokens=r.output_tokens or 0),
                               model=r.model)

    def count_tokens(self,**kwargs):
        raise RuntimeError("Exact token count unavailable on Ollama. Do not invent an exact count.")

class Client:
    def __init__(self,provider):
        self.messages=MessageAPI(provider)

def make_client():
    if PROVIDER=="ollama":
        return Client(OllamaProvider(model=MODEL,host=os.environ.get("OLLAMA_HOST","http://localhost:11434")))
    if PROVIDER=="anthropic":
        return Client(AnthropicProvider(model=MODEL))
    raise ValueError("FDE_PROVIDER must be ollama or anthropic")
