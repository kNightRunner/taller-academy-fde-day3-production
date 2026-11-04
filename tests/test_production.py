"""Offline safety, boundary and scorer regression tests (37 checks)."""
from __future__ import annotations
import unittest
from unittest.mock import patch
import copy
import guardrails as G
import tools_lab as T
import retrieval_agent as R
import eval_harness as E

class ProductionTests(unittest.TestCase):
    def setUp(self):
        G.REFUNDS_ISSUED.clear()
        G.AUDIT_LOG.clear()
        T.BOOKED.clear()
        T.BUSY.clear()
        T.BUSY.update({
            "ana":[("2026-04-06",9,11),("2026-04-07",14,16)],
            "ben":[("2026-04-06",13,15)],
            "cai":[("2026-04-06",9,10),("2026-04-07",9,12)],
        })
    def valid_booking(self,start=10,duration=1):
        return T.book_meeting(["ana","ben"],"2026-11-10",start,duration,"Design review")
    def gate(self,tool,args,state=None):
        return G.guarded_call(tool,args,state or {"refunds":0,"refunded_usd":0})

def add(name,fn):
    def test(self):
        self.assertTrue(fn(self),name)
    setattr(ProductionTests,"test_"+name,test)

def refund(amount=100,order="4471",reason="duplicate charge"):
    return {"order_id":order,"amount_usd":amount,"reason":reason}

checks={
"01_unknown_validation_rule":lambda s: G.validate("delete_account",{}) is not None,
"02_read_empty_id":lambda s: G.validate("get_order",{"order_id":" "}) is not None,
"03_read_integer_id":lambda s: G.validate("get_order",{"order_id":12}) is not None,
"04_charge_empty_id":lambda s: G.validate("get_charge_history",{"order_id":""}) is not None,
"05_refund_unknown_order":lambda s: G.validate("issue_refund",refund(order="0000")) is not None,
"06_refund_negative":lambda s: G.validate("issue_refund",refund(-5)) is not None,
"07_refund_zero":lambda s: G.validate("issue_refund",refund(0)) is not None,
"08_refund_string_amount":lambda s: G.validate("issue_refund",refund("100")) is not None,
"09_refund_bool_amount":lambda s: G.validate("issue_refund",refund(True)) is not None,
"10_refund_blank_reason":lambda s: G.validate("issue_refund",refund(reason="   ")) is not None,
"11_refund_above_charges":lambda s: G.validate("issue_refund",refund(100000)) is not None,
"12_threshold_below":lambda s: not G.is_high_stakes("issue_refund",refund(499)),
"13_threshold_at":lambda s: G.is_high_stakes("issue_refund",refund(500)),
"14_read_no_approval":lambda s: not G.is_high_stakes("get_order",{"order_id":"4471"}),
"15_threshold_above":lambda s: G.is_high_stakes("issue_refund",refund(1000)),
"16_unpermitted_tool":lambda s: "not permitted" in s.gate("delete_account",{}).get("error",""),
"17_invalid_refund_gate":lambda s: "BLOCKED" in s.gate("issue_refund",refund(-1)).get("error",""),
"18_total_cap":lambda s: "BLOCKED" in s.gate("issue_refund",refund(200),{"refunds":0,"refunded_usd":1950}).get("error",""),
"19_refund_count_cap":lambda s: "BLOCKED" in s.gate("issue_refund",refund(200),{"refunds":2,"refunded_usd":0}).get("error",""),
"20_reject_approval":lambda s: rejected_gate(s),
"21_accept_approval":lambda s: approved_gate(s),
"22_start_eight_rejected":lambda s: "error" in s.valid_booking(8,1),
"23_start_nine_allowed":lambda s: "booked" in s.valid_booking(9,1),
"24_start_seventeen_allowed":lambda s: "booked" in s.valid_booking(17,1),
"25_start_eighteen_rejected":lambda s: "error" in s.valid_booking(18,1),
"26_duration_zero_rejected":lambda s: "error" in s.valid_booking(10,0),
"27_duration_one_allowed":lambda s: "booked" in s.valid_booking(10,1),
"28_duration_four_allowed":lambda s: "booked" in s.valid_booking(10,4),
"29_duration_five_rejected":lambda s: "error" in s.valid_booking(10,5),
"30_past_working_hours":lambda s: "error" in s.valid_booking(17,2),
"31_empty_search":lambda s: "error" in R.search_documents(""),
"32_stopword_search":lambda s: "error" in R.search_documents("the and"),
"33_top_k_validation":lambda s: "error" in R.search_documents("contract",9),
"34_scorer_correct":lambda s: scorer_correct(),
"35_scorer_swapped":lambda s: scorer_swapped(),
"36_duplicate_search_process":lambda s: not E.check_process(E.EVAL_SET[0],{"queries":["same","same"],"steps":[],"hit_step_limit":False,"answer":"answer"})["clean"],
"37_step_limit_process":lambda s: not E.check_process(E.EVAL_SET[2],{"queries":["x"],"steps":[],"hit_step_limit":True,"answer":"Incomplete"})["clean"],
}

def rejected_gate(s):
    with patch.object(G,"request_approval",return_value=(False,"manager sign-off needed")):
        result=s.gate("issue_refund",refund(840))
    return "CANCELLED" in result.get("error","") and not G.REFUNDS_ISSUED

def approved_gate(s):
    with patch.object(G,"request_approval",return_value=(True,"approved")):
        result=s.gate("issue_refund",refund(840))
    return "refunded" in result and len(G.REFUNDS_ISSUED)==1

def scorer_correct():
    case=E.EVAL_SET[1]
    trace={"answer":"Acme Compute consumption is USD 288,500 [doc-03]. Support costs USD 2,000 per month [doc-07], or USD 24,000 per year. Total annual cost is USD 312,500."}
    return E.check_outcome(case,trace)["passed_all"]

def scorer_swapped():
    case=E.EVAL_SET[1]
    trace={"answer":"Acme Compute consumption is USD 312,500 [doc-03]. Support is USD 2,000 per month [doc-07]. Total annual cost is USD 288,500. The figure 24,000 is mentioned."}
    return not E.check_outcome(case,trace)["passed_all"]

for name,fn in checks.items():
    add(name,fn)
if __name__=="__main__":
    unittest.main()
