"""Export one production job (Supabase management SQL API) as a test fixture.

Usage: python -I backend/scripts/export_prod_job_fixture.py <job_id> "<note>" > fixture.json
The Authorization header is injected by the session proxy; never put a real token here.
Exports public video content and public PubMed records only: no user ids, emails,
reviewer ids or storage paths."""
import json,sys,urllib.request,urllib.error
def q(sql):
    r=urllib.request.Request("https://api.supabase.com/v1/projects/kscfszhdrlsbpsqwfirv/database/query",data=json.dumps({"query":sql}).encode(),headers={"Content-Type":"application/json","User-Agent":"curl/8","Authorization":"Bearer dummy"},method="POST")
    import time
    for i in range(8):
        try: return json.load(urllib.request.urlopen(r))
        except urllib.error.HTTPError as e:
            if e.code!=429: raise
            time.sleep(5*(i+1))
    raise SystemExit("rate limited")
def lit(s): return "'"+s.replace("'","''")+"'"
jid=sys.argv[1]; note=sys.argv[2]
job=q(f"select j.id,j.previous_job_id,j.created_at,v.filename from jobs j join videos v on v.id=j.video_id where j.id={lit(jid)}")[0]
res=q(f"select label,misinfo_basis,decision_rule,deciding_claim_ids,confidence,explanation,pipeline,pipeline_version,fallback_reason,routing_snapshot from results where job_id={lit(jid)} order by created_at desc limit 1")[0]
rev=q(f"select status,reasons,rules_fired,proposed_label,policy_version,severity,claim_severities from human_reviews where job_id={lit(jid)} order by created_at desc limit 1")
segs=q(f"select segment_id,start_seconds,end_seconds,text from transcript_segments where job_id={lit(jid)} order by start_seconds,segment_id")
ocr=q(f"select segment_id,start_seconds,end_seconds,text,confidence from ocr_segments where job_id={lit(jid)} order by start_seconds,segment_id")
claims=q(f"select id,claim_id,text,category,claim_kind,label,deciding,start_seconds,end_seconds,source_segment_ids,requires_verification,search_trail from claims where job_id={lit(jid)}")
claims.sort(key=lambda c:int(c['claim_id'].lstrip('c') or 0) if c['claim_id'].lstrip('c').isdigit() else 999)
out=[]
for c in claims:
    pk=lit(c['id'])
    st=q(f"select stance,segment_ids,rationale,model,prompt_version from claim_stances where claim_pk={pk}")
    vr=q(f"select verdict,explanation,limitations,raw_confidence,revisions,retrieval_attempts,model,prompt_version from verification_results where claim_pk={pk}")
    cr=q(f"select decision,issues,checks,requires_review,model,prompt_version from critic_reviews where claim_pk={pk}")
    ev=q(f"select e.evidence_id,e.pmid,e.doi,e.source,e.title,e.abstract,e.publication_year as year,e.publication_type,e.study_type,e.publisher,ce.relation,ce.rank,ce.relevance_score as relevance from claim_evidence ce join evidence_records e on e.id=ce.evidence_pk where ce.claim_pk={pk} order by ce.rank")
    v=vr[0] if vr else {}
    for k in ('search_trail','source_segment_ids'):
        if isinstance(c.get(k),str):
            try: c[k]=json.loads(c[k])
            except Exception: pass
    d={k:c[k] for k in ('claim_id','text','category','claim_kind','label','deciding','start_seconds','end_seconds','source_segment_ids','requires_verification','search_trail')}
    d.update(stances=st, verdict=v.get('verdict'), explanation=v.get('explanation'), limitations=v.get('limitations'),
             raw_confidence=v.get('raw_confidence'), revisions=v.get('revisions'), retrieval_attempts=v.get('retrieval_attempts'),
             verifier_model=v.get('model'), verifier_prompt_version=v.get('prompt_version'), critic_reviews=cr, evidence=ev)
    out.append(d)
def j(x):
    if isinstance(x,str):
        try: return json.loads(x)
        except Exception: return x
    return x
for k in ('deciding_claim_ids','routing_snapshot'): res[k]=j(res.get(k))
r0=rev[0] if rev else None
if r0:
    for k in ('reasons','rules_fired','claim_severities'): r0[k]=j(r0.get(k))
fix={"_provenance":f"COPIED FROM PRODUCTION (Supabase infodemic-prod) by the coordinating session on 2026-11-28: job {jid[:8]} of the labmuffin benzene video (golden tune v135, golden NO_MISINFO). {note} Public video content and public PubMed records only: no user ids, emails, reviewer ids or storage paths.",
     "job_id_prefix":jid[:8],"previous_job_prefix":(job['previous_job_id'] or '')[:8] or None,"filename":job['filename'],"golden_video_id":"v135","golden_label":"NO_MISINFO",
     "result":res,"review":r0,"transcript_segments":segs,"ocr_segments":ocr,"claims":out}
print(json.dumps(fix,indent=1,ensure_ascii=False,default=str))
