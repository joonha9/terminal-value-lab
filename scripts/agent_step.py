"""Create agent runs or advance each by one stage (independent runs advance in parallel).

    python3 -P scripts/agent_step.py --new a1 a2 a3 a4 a5   # create runs, write gen-1 proposer briefs
    python3 -P scripts/agent_step.py --runs a1 a2 a3 a4 a5  # process any replies that are ready

The orchestrator passes each brief's text to a tool-less subagent and saves the reply text as
proposals.txt / verdicts.txt in that generation folder. For each run: when proposals.txt exists,
proposals are validated and the critic brief is written; when verdicts.txt exists, approved
recipes are graded (exploration, truth M) and the next proposer brief is written.

Every reply, including ones that cannot be parsed or applied, is logged in replies.jsonl. A bad
reply is renamed (proposals.rejected-N.txt) and the same brief must be re-run. A stage either
completes fully (records + state written together) or changes nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import agents as ag  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--new", nargs="*", default=[])
ap.add_argument("--runs", nargs="*", default=[])
ap.add_argument("--model", default="claude-opus-5-5", help="model of the proposer/critic subagents (recorded)")
ap.add_argument("--agent", default="tv-text-only", help="subagent definition used (recorded)")
a = ap.parse_args()


def brief(run: ag.Run, g: int) -> tuple[Path, dict]:
    p = run.gen_dir(g) / "proposer_prompt.md"
    p.write_text(ag.proposer_prompt(run, g))
    return p, {"generation": g, "stage": "awaiting_proposals"}


def set_aside(f: Path, run: ag.Run, g: int, kind: str, err: str) -> None:
    text = f.read_text()
    run.log_reply(g, kind, text, ok=False, error=err)
    n = 1
    while (f.parent / f"{f.stem}.rejected-{n}.txt").exists():
        n += 1
    f.rename(f.parent / f"{f.stem}.rejected-{n}.txt")
    print(f"{run.name} gen{g}: {kind} reply not usable ({err}); logged, re-run the same brief")


for name in a.new:
    run = ag.Run(name, {"model": a.model, "agent_definition": a.agent})
    p, st = brief(run, 1)
    run.save_state(st)
    print(f"{name} gen1: PROPOSER {p.relative_to(ROOT)}")

for name in a.runs:
    run = ag.Run(name)
    st, g = run.state, run.state["generation"]
    gd = run.gen_dir(g) if g else None
    if st["stage"] == "awaiting_proposals" and (gd / "proposals.txt").exists():
        f = gd / "proposals.txt"
        try:
            reply = ag.parse_json_reply(f.read_text())
            archive_now, pending = ag.register_proposals(run, reply, g)
        except (ValueError, ag.ReplyError) as e:
            set_aside(f, run, g, "proposals", str(e))
            continue
        run.log_reply(g, "proposals", f.read_text(), ok=True)
        (gd / "pending.json").write_text(json.dumps(pending, indent=1))
        if run.config["critic"] and pending:
            (gd / "critic_prompt.md").write_text(ag.critic_prompt(run, pending))
            run.commit(archive_now, {"generation": g, "stage": "awaiting_verdicts"})
            print(f"{name} gen{g}: {len(pending)} to critic -> CRITIC {(gd / 'critic_prompt.md').relative_to(ROOT)}")
            continue
        records = archive_now + ag.grade_verdicts(pending, ag.check_verdicts(None, len(pending)))
    elif st["stage"] == "awaiting_verdicts" and (gd / "verdicts.txt").exists():
        f = gd / "verdicts.txt"
        pending = json.loads((gd / "pending.json").read_text())
        try:
            verdicts = ag.check_verdicts(ag.parse_json_reply(f.read_text()), len(pending))
        except (ValueError, ag.ReplyError) as e:
            set_aside(f, run, g, "verdicts", str(e))
            continue
        run.log_reply(g, "verdicts", f.read_text(), ok=True)
        records = ag.grade_verdicts(pending, verdicts)
    else:
        print(f"{name}: waiting ({st})")
        continue
    best = [r["explore"]["median_abs"] for r in records if r.get("explore")]
    if g < run.config["generations"]:
        run.commit(records, st)            # archive first so the next brief sees these records
        p, nst = brief(run, g + 1)
        run.save_state(nst)
        nxt = f" -> PROPOSER {p.relative_to(ROOT)}"
    else:
        run.commit(records, {"generation": g, "stage": "complete"})
        nxt = f"; search complete {ag.funnel(run.archive())}"
    print(f"{name} gen{g}: graded {len(best)}" + (f", best {min(best):.3f}" if best else "") + nxt)
