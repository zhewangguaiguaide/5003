"""Check policy research references and render views; never certify policy truth."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- GENERATED POLICY VIEWS: edit catalog.json, then run scripts.check_policy_assets --render -->"


class PolicyError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PolicyError(message)


def indexed(rows, label):
    require(isinstance(rows, list) and bool(rows), f"{label}: expected nonempty list")
    result = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"],
                f"{label}: missing id")
        require(row["id"] not in result, f"{label}: duplicate id")
        result[row["id"]] = row
    return result


def validate_catalog(catalog, *, require_ready=False, corpus_path=None):
    categories = indexed(catalog["categories"], "categories")
    sources = indexed(catalog["sources"], "sources")
    rules = indexed(catalog["rules"], "rules")
    flows = indexed(catalog["workflows"], "workflows")
    for source in sources.values():
        parts = urlsplit(source["url"])
        host = parts.hostname or ""
        require(parts.scheme == "https" and (host == "cityu.edu.hk" or host.endswith(".cityu.edu.hk"))
                and parts.username is None and not parts.fragment, "sources: expected official HTTPS URL")
        require(source["access"] in ("official_full_text", "official_index", "link_only"),
                "sources: unknown access level")
        require(bool(source["locator"]) and date.fromisoformat(source["checked_on"]) <= date.fromisoformat(catalog["as_of"]),
                "sources: missing locator or future check date")
        require(source["in_research_corpus"] == (source["local_record"] is not None),
                "sources: local record match inconsistent")
    for rule in rules.values():
        require(rule["topics"] and set(rule["topics"]) <= categories.keys(), "rules: unknown topic")
        require(rule["source_ids"] and set(rule["source_ids"]) <= sources.keys(), "rules: missing source reference")
        require(rule["audience"] and rule["statement"] and rule["qualifications"], "rules: missing scope or qualifications")
        require(rule["review_status"] in ("candidate", "reviewed"), "rules: unknown review status")
        require(rule["kind"] in ("official_summary", "research_guard"), "rules: unknown statement kind")
        if rule["review_status"] == "reviewed":
            require({"role2", "role6"} <= set(rule["reviewer_roles"]), "rules: reviewed needs role2/role6 markers")
            for sid in rule["source_ids"]:
                source = sources[sid]
                require(source["access"] == "official_full_text" and
                        re.fullmatch(r"[0-9a-f]{64}", source["official_snapshot_sha256"] or "") and
                        bool(source["short_quote"]), "rules: reviewed needs full source snapshot and evidence")
    for flow in flows.values():
        require(flow["category"] in categories and flow["status"] == "advisory_draft", "flows: invalid category/status")
        nodes = indexed(flow["nodes"], "flow nodes")
        outgoing = {nid: [] for nid in nodes}
        for node in nodes.values():
            require(set(node["rule_ids"]) <= rules.keys(), "flows: unknown rule reference")
            require(node["kind"] in ("context", "policy", "end"), "flows: unknown node kind")
            if node["kind"] == "policy":
                require(bool(node["rule_ids"]), "flows: policy node needs rule reference")
        for edge in flow["edges"]:
            require(edge["source"] in nodes and edge["target"] in nodes, "flows: dangling edge")
            outgoing[edge["source"]].append(edge["target"])
        seen, queue = set(), [flow["nodes"][0]["id"]]
        while queue:
            current = queue.pop()
            if current not in seen:
                seen.add(current)
                queue.extend(outgoing[current])
        require(seen == nodes.keys(), "flows: unreachable node")
        require(any(node["kind"] == "end" for node in nodes.values()), "flows: no end node")
        require(all(outgoing[nid] or nodes[nid]["kind"] == "end" for nid in nodes), "flows: unlabelled dead end")
        # Reachability from the start alone does not detect an inescapable cycle.
        can_finish = {nid for nid, node in nodes.items() if node["kind"] == "end"}
        while True:
            previous = len(can_finish)
            can_finish.update(nid for nid in nodes if any(target in can_finish for target in outgoing[nid]))
            if len(can_finish) == previous:
                break
        require(can_finish == nodes.keys(), "flows: branch cannot reach an end node")
    schedule = indexed(catalog["payment_schedule"], "payment schedule")
    for row in schedule.values():
        require(row["charging_basis"] in ("flat", "per_credit") and row["term"] in ("A", "B", "Summer"),
                "payment schedule: missing charging basis or term")
        require(row["statement_number"] in (None, 1, 2) and
                (row["charging_basis"] != "flat" or row["statement_number"] is None),
                "payment schedule: invalid statement number")
        require(bool(re.fullmatch(r"\d{4}-\d{4}", row["academic_year"])), "payment schedule: invalid academic year")
        start, end = map(int, row["academic_year"].split("-"))
        require(end == start + 1 and date.fromisoformat(row["due_date"]).year in (start, end),
                "payment schedule: due date outside academic years")
        require(row["status"] in ("candidate", "reviewed") and row["source_ids"] and row["rule_ids"] and
                set(row["source_ids"]) <= sources.keys() and set(row["rule_ids"]) <= rules.keys(),
                "payment schedule: missing evidence or rule reference")
        evidence = {sid for rid in row["rule_ids"] for sid in rules[rid]["source_ids"]}
        require(set(row["source_ids"]) <= evidence, "payment schedule: evidence not bound to referenced rules")
    for item in indexed(catalog["open_items"], "open items").values():
        require(item["stage"] in ("before_release", "later") and item.get("status", "open") in ("open", "resolved"),
                "open items: unknown stage/status")
        require(item["owner_roles"] and set(item["owner_roles"]) <= {f"role{i}" for i in range(1, 7)} and
                set(item["source_ids"]) <= sources.keys() and set(item["rule_ids"]) <= rules.keys(),
                "open items: missing owner or dangling reference")
        require(item["issue"] and item["exit_criteria"] and item["downstream"], "open items: missing acceptance or impact")
    if require_ready:
        require(corpus_path is not None and corpus_path.is_file(), "ready gate: explicit accepted corpus file required")
        require(catalog["corpus"]["acceptance"] == "accepted" and catalog["corpus"]["publication_workspace_received"],
                "ready gate: accepted snapshot markers missing")
        require(hashlib.sha256(corpus_path.read_bytes()).hexdigest() == catalog["corpus"]["research_sha256"],
                "ready gate: corpus SHA mismatch")
        require(all(r["review_status"] == "reviewed" for r in rules.values()), "ready gate: candidate rules remain")
        require(all(row["status"] == "reviewed" for row in schedule.values()), "ready gate: candidate schedule rows remain")
        require(not any(item["stage"] == "before_release" and item.get("status", "open") != "resolved"
                        for item in catalog["open_items"]), "ready gate: release blockers remain")
        docs = {r["url"].rstrip("/"): r for r in
                (json.loads(line) for line in corpus_path.read_text(encoding="utf-8-sig").splitlines() if line.strip())}
        for sid in {sid for rule in rules.values() for sid in rule["source_ids"]}:
            source = sources[sid]
            doc = docs.get(source["url"].rstrip("/"))
            require(doc is not None and source["short_quote"] in doc["content"],
                    "ready gate: supporting source/quote absent from accepted corpus")
            require(source["local_record"] is not None and hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
                    == source["local_record"]["content_sha256"], "ready gate: source content binding mismatch")
    return dict(sources=len(sources), rules=len(rules), workflows=len(flows),
                candidate_rules=sum(r["review_status"] == "candidate" for r in rules.values()),
                full_text_sources=sum(s["access"] == "official_full_text" for s in sources.values()),
                schedule_rows=len(schedule), open_items=len(catalog["open_items"]))


def safe_label(value):
    return value.replace("\n", " ").replace('"', "＂").replace("|", "／").replace("<", "＜").replace(">", "＞")


def render_views(catalog):
    categories = {c["id"]: c["label"] for c in catalog["categories"]}
    sources = {s["id"]: s for s in catalog["sources"]}
    lines = ["", f"## 分类制度与规则表（{len(catalog['rules'])}条）", "", "本版规则状态均为研究候选；后续状态以catalog记录为准。英文statement见catalog，表内保留适用条件与例外。", "",
             "| 规则／主题 | 内容与适用对象 | 限制、例外及来源 |", "|---|---|---|"]
    for rule in catalog["rules"]:
        topics = "、".join(categories[k] for k in rule["topics"])
        kind = "研究核对规则" if rule["kind"] == "research_guard" else "官网候选摘要"
        values = [rule["id"] + "／" + topics + "（" + kind + "）", rule["summary_zh"] + "；" + rule["audience"],
                  rule["qualifications"] + " 来源：" + ", ".join(rule["source_ids"])]
        lines.append("| " + " | ".join(safe_label(v) for v in values) + " |")
    schedule_sources = {sid for row in catalog["payment_schedule"] for sid in row["source_ids"]}
    has_full_schedule = all(sources[sid]["access"] == "official_full_text" and sources[sid]["official_snapshot_sha256"]
                            for sid in schedule_sources)
    evidence_note = "日期按已取得的官网全文登记" if has_full_schedule else "日期来源层级见来源表，索引不等于完整原文"
    lines += ["", "## 2026/27付款表的条件化登记", "",
              evidence_note + "，仍为待人工批准的候选；日期状态只相对于本目录核查日，不代表个人欠费。接受费另按本人offer核对；本表不计算个人费用。", "",
              "| 学期 | 收费口径／账单 | 表列日期 | 相对核查日 | 规则／来源 |", "|---|---|---|---|---|"]
    as_of = date.fromisoformat(catalog["as_of"])
    for row in catalog["payment_schedule"]:
        due = date.fromisoformat(row["due_date"])
        state = "已过" if due < as_of else "未来" if due > as_of else "当日"
        basis = "flat整笔学费" if row["charging_basis"] == "flat" else "按学分"
        number = row["statement_number"]
        bill = "／第" + str(number) + "次账单" if number else ""
        lines.append("| " + " | ".join([row["term"], basis + bill, row["due_date"], state,
                      ", ".join(row["rule_ids"] + row["source_ids"])]) + " |")
    lines += ["", "按学分收费还区分入学届别的预缴／抵扣安排；A/B晚申请的两学分最低额、Summer分段和continuation fee见R22、R24、R40。SGS细则对Summer也写最低额，FO暑期表未重复该脚注，不能自行当作豁免。申请程序add/drop与收费Week 2分界分别核专业日历（R41）。", "",
              "## 八个目标流程（研究导航图）", "",
              "各图以条件已补齐为前提；条件缺失先澄清。节点中的R编号回查上表，跨主题流程不是单一栏目的顺序清单。", ""]
    for flow in catalog["workflows"]:
        lines += ["### " + flow["id"] + " " + flow["title"], "", "```mermaid", "flowchart TD"]
        for node in flow["nodes"]:
            suffix = "（" + "/".join(node["rule_ids"]) + "）" if node["rule_ids"] else ""
            lines.append('    ' + node["id"] + '["' + safe_label(node["label"] + suffix) + '"]')
        for edge in flow["edges"]:
            middle = " -->|" + safe_label(edge["condition"]) + "| " if edge["condition"] else " --> "
            lines.append("    " + edge["source"] + middle + edge["target"])
        lines += ["```", ""]
    lines += ["## 官方来源登记与核实状态", "", "A＝本轮完整正文可读；B＝官网索引支持；L＝仅确认入口。均不自动代表现行有效或人工批准。", "",
              "| ID／来源 | 层级及实时结果 | 研究快照对齐 | 定位与待核事项 |", "|---|---|---|---|"]
    levels = {"official_full_text": "A", "official_index": "B", "link_only": "L"}
    for source in catalog["sources"]:
        match = "独立正文第" + str(source["local_record"]["line"]) + "行" if source["in_research_corpus"] else "未按该URL对齐"
        link = "[" + source["id"] + " " + source["title"] + "](" + source["url"] + ")"
        lines.append("| " + link + " | " + levels[source["access"]] + "／" + source["live_result"] + " | " + match
                     + " | " + safe_label(source["locator"] + "；" + source["observation"]) + " |")
    lines += ["", "## 必须补齐与可留后续的工作", "",
              "“发布前必须补齐”只阻塞该行列出的正式结论；允许先做有待核分支的导航、接口、mock及评测工具。“后续工作”仍有本岗位的正式验收前置，不表示可以跳过。", "",
              "| 项目／阶段 | 主责 | 缺口与完成条件 | 阻塞范围／可并行工作 |", "|---|---|---|---|"]
    roles = {f"role{i}": str(i) + "号位" for i in range(1, 7)}
    for item in catalog["open_items"]:
        stage = "发布前必须补齐" if item["stage"] == "before_release" else "可留后续岗位"
        values = [item["id"] + "／" + stage, "、".join(roles[r] for r in item["owner_roles"]),
                  item["issue"] + " 完成条件：" + item["exit_criteria"], item["downstream"]]
        lines.append("| " + " | ".join(safe_label(v) for v in values) + " |")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--corpus", type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = json.loads((ROOT / "knowledge/catalog.json").read_text(encoding="utf-8"))
        summary = validate_catalog(catalog, require_ready=args.require_ready, corpus_path=args.corpus)
        readme = ROOT / "knowledge/README.md"
        text = readme.read_text(encoding="utf-8")
        require(text.count(MARKER) == 1, "README: missing/duplicate generated section marker")
        expected = text.split(MARKER)[0] + MARKER + "\n" + render_views(catalog)
        if args.render:
            readme.write_bytes(expected.encode("utf-8"))
        else:
            require(text == expected, "README view differs; run --render")
    except (PolicyError, KeyError, TypeError, ValueError, OSError) as error:
        print("FAIL:", str(error) if isinstance(error, PolicyError) else type(error).__name__)
        return 1
    print(json.dumps(summary, ensure_ascii=False))
    print("STRUCTURE ONLY: no policy truth, human approval, runnable RAG or performance acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
