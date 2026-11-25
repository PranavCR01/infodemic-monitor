"""Write model_relabel_claims.csv and model_relabel_videos.csv from
model_relabel_data.py. video_level_label, misinfo_basis and review_reasons
are derived with scripts/judge.py, never hand-typed."""
import csv, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import judge
from model_relabel_data import CLAIMS, VIDEOS

ANN = "blind_model_pass_v1"
CC = ["video_id","claim_id","claim_text","claim_source","claim_kind","start_seconds","end_seconds","speaker_stance","claim_verdict","evidence_supporting","evidence_contradicting","annotator","confidence","review_status","reviewer","reviewer_notes","notes"]
VC = ["video_id","source_url","platform","topic","video_level_label","misinfo_basis","review_reasons","text_type","case_tags","split","annotator","confidence","review_status","reviewer","reviewer_notes","notes","source","external_label","external_source","external_url"]

rows = []
for (v,c,t,src,kind,s,e,st,vd,sup,con,conf,notes) in CLAIMS:
    assert st in judge.STANCES and vd in judge.VERDICTS and kind in judge.CLAIM_KINDS, (v,c)
    if vd == "UNSUPPORTED":
        assert st == "ENDORSES" and not sup and not con and notes.startswith("UNSUPPORTED ("), (v,c)
    if vd in ("SUPPORTED",): assert sup, (v,c)
    if vd == "CONTRADICTED": assert con, (v,c)
    if vd == "MIXED": assert sup and con, (v,c)
    rows.append(dict(zip(CC,[v,c,t,src,kind,s,e,st,vd,sup,con,ANN,conf,"pending","","",notes])))

vids = [v[0] for v in VIDEOS]
assert len(vids) == 41 and len(set(vids)) == 41
assert {r["video_id"] for r in rows} <= set(vids)
with open(os.path.join(HERE,"model_relabel_claims.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, CC); w.writeheader(); w.writerows(rows)

out = []
for (v,topic,tt,tags,conf,notes) in VIDEOS:
    cl = [r for r in rows if r["video_id"] == v]
    label, basis, _dec, _r = judge.judge(cl)
    reasons = judge.review_reasons(cl)
    tagl = [x for x in tags.split(";") if x]
    if judge.is_mixed(cl) and "mixed" not in tagl: tagl.append("mixed")
    if "out_of_scope" in tagl: assert tagl == ["out_of_scope"] and not cl, v
    if not cl and "no checkable" not in notes and "out_of_scope" not in tagl:
        notes = ("no checkable claims; " + notes).strip("; ")
    out.append(dict(zip(VC,[v,"","",topic,label,basis or "",";".join(reasons),tt,";".join(tagl),"",ANN,conf,"pending","","",notes,"","","",""])))
with open(os.path.join(HERE,"model_relabel_videos.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, VC); w.writeheader(); w.writerows(out)
print(len(rows),"claims;",len(out),"videos")
for o in out: print(o["video_id"],o["video_level_label"],o["misinfo_basis"],o["review_reasons"])
