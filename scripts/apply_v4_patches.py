#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 v4 — 幂等 AST 校验补丁器 (apply_v4_patches.py)

在保留 v3 全部 16 项架构安全红线的前提下，将 SessionAttachmentManager 无损接入：
1. backend/orchestrator.py：
   - RoundtableOrchestrator 初始化与会话删除联动清理会话附件目录
   - _append_non_agent_message / start_topic_meeting / chair_interrupt / build_session_export_bytes
     原生持久化消息级 attachments 与会话白板级 session_attachments
2. backend/cli_adapters.py：
   - WarmAntigravityProcess.stream_turn、UnifiedAgentRunner.stream_discussion_turn、
     _stream_with_fallback、_stream_raw_cli 与 stream_agent_execution 在每次 CLI 调用前
     自动将当前会话的图片与文件附件只读隔离挂载至席位专属 TMPDIR/rt_attachments/，
     并为支持 --image 的 Codex CLI 自动附加图像参数。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _replace_once(src: str, old: str, new: str, label: str) -> str:
    if new in src:
        return src
    if old not in src:
        raise RuntimeError(f"[apply_v4_patches] 未找到预期锚点 ({label})")
    return src.replace(old, new, 1)


def patch_orchestrator(orch_path: Path) -> bool:
    orig = orch_path.read_text(encoding="utf-8")
    src = orig

    # 1. 导入 SessionAttachmentManager
    src = _replace_once(
        src,
        "from .storage import RoundtableSQLiteStore\n",
        "from .attachments import SessionAttachmentManager\nfrom .storage import RoundtableSQLiteStore\n",
        "orchestrator.import_attachments",
    )

    # 2. __init__ 挂载 self.attachments 与 self.runner.attachments
    src = _replace_once(
        src,
        "        self.settings = RuntimeSettings.create_default(workspace_dir=workspace_dir)\n"
        "        self._load_persisted_config()\n"
        "        self.runner = UnifiedAgentRunner(self.settings)\n",
        "        self.settings = RuntimeSettings.create_default(workspace_dir=workspace_dir)\n"
        "        self._load_persisted_config()\n"
        "        self.attachments = SessionAttachmentManager(self.data_dir)\n"
        "        self.runner = UnifiedAgentRunner(self.settings)\n"
        "        self.runner.attachments = self.attachments\n",
        "orchestrator.init_attachments",
    )

    # 3. delete_session 同步清理会话附件仓
    src = _replace_once(
        src,
        "        del self.sessions[session_id]\n        self.store.delete_session(session_id, wait=True)\n",
        "        del self.sessions[session_id]\n"
        "        self.attachments.delete_session_attachments(session_id)\n"
        "        self.store.delete_session(session_id, wait=True)\n",
        "orchestrator.delete_session_attachments",
    )

    # 4. _append_non_agent_message 支持 attachments 元数据列表
    src = _replace_once(
        src,
        "    async def _append_non_agent_message(\n"
        "        self,\n"
        "        sess: MeetingSession,\n"
        "        speaker: str,\n"
        "        speaker_name: str,\n"
        "        role_title: str,\n"
        "        phase_label: str,\n"
        "        content: str,\n"
        "        badge: str = \"\",\n"
        "        error: bool = False,\n"
        "    ) -> dict:\n"
        "        sess.updated_ts = time.time()\n"
        "        msg = {\n"
        "            \"id\": f\"m_{uuid.uuid4().hex[:8]}\",\n"
        "            \"speaker\": speaker,\n"
        "            \"speaker_name\": speaker_name,\n"
        "            \"role_title\": role_title,\n"
        "            \"phase_label\": phase_label,\n"
        "            \"content\": content,\n"
        "            \"badge\": badge,\n"
        "            \"target\": None,\n"
        "            \"ttft_ms\": 0,\n"
        "            \"elapsed_ms\": 0,\n"
        "            \"streaming\": False,\n"
        "            \"error\": error,\n"
        "            \"timestamp\": now_hhmmss(),\n"
        "        }\n",
        "    async def _append_non_agent_message(\n"
        "        self,\n"
        "        sess: MeetingSession,\n"
        "        speaker: str,\n"
        "        speaker_name: str,\n"
        "        role_title: str,\n"
        "        phase_label: str,\n"
        "        content: str,\n"
        "        badge: str = \"\",\n"
        "        error: bool = False,\n"
        "        attachments: Optional[List[dict]] = None,\n"
        "    ) -> dict:\n"
        "        sess.updated_ts = time.time()\n"
        "        msg = {\n"
        "            \"id\": f\"m_{uuid.uuid4().hex[:8]}\",\n"
        "            \"speaker\": speaker,\n"
        "            \"speaker_name\": speaker_name,\n"
        "            \"role_title\": role_title,\n"
        "            \"phase_label\": phase_label,\n"
        "            \"content\": content,\n"
        "            \"badge\": badge,\n"
        "            \"attachments\": list(attachments) if attachments else [],\n"
        "            \"target\": None,\n"
        "            \"ttft_ms\": 0,\n"
        "            \"elapsed_ms\": 0,\n"
        "            \"streaming\": False,\n"
        "            \"error\": error,\n"
        "            \"timestamp\": now_hhmmss(),\n"
        "        }\n",
        "orchestrator.append_non_agent_message",
    )

    # 5. start_topic_meeting 接入 attachments 并写入 whiteboard["session_attachments"]
    src = _replace_once(
        src,
        "        executor_agent: Optional[str] = None,\n"
        "        reset_history: bool = False,\n"
        "    ) -> None:\n"
        "        await self.cancel_active_flow(sess, reason_tag=\"切换新议题\")\n"
        "        sess.round_driver_records.clear()\n"
        "        await self.runner.reset_session_context(sess.session_id)\n"
        "        draft_items = list(sess.whiteboard.get(\"items\") or []) if not sess.messages and not reset_history else []\n",
        "        executor_agent: Optional[str] = None,\n"
        "        reset_history: bool = False,\n"
        "        attachments: Optional[List[dict]] = None,\n"
        "    ) -> None:\n"
        "        await self.cancel_active_flow(sess, reason_tag=\"切换新议题\")\n"
        "        sess.round_driver_records.clear()\n"
        "        await self.runner.reset_session_context(sess.session_id)\n"
        "        draft_items = list(sess.whiteboard.get(\"items\") or []) if not sess.messages and not reset_history else []\n"
        "        prev_atts = list(sess.whiteboard.get(\"session_attachments\") or []) if not reset_history else []\n"
        "        merged_atts: List[dict] = []\n"
        "        seen_att_ids: set = set()\n"
        "        for att_it in prev_atts + list(attachments or []):\n"
        "            if isinstance(att_it, dict) and att_it.get(\"id\") and att_it[\"id\"] not in seen_att_ids:\n"
        "                seen_att_ids.add(att_it[\"id\"])\n"
        "                merged_atts.append(att_it)\n",
        "orchestrator.start_topic_sig",
    )

    src = _replace_once(
        src,
        "        chair_msg = await self._append_non_agent_message(\n"
        "            sess,\n"
        "            speaker=\"chair\",\n"
        "            speaker_name=\"主持人\",\n"
        "            role_title=\"发起议题\",\n"
        "            phase_label=\"议题\",\n"
        "            content=sess.topic,\n"
        "            badge=COLLAB_MODES[sess.collab_mode][\"label\"],\n"
        "        )\n",
        "        chair_msg = await self._append_non_agent_message(\n"
        "            sess,\n"
        "            speaker=\"chair\",\n"
        "            speaker_name=\"主持人\",\n"
        "            role_title=\"发起议题\",\n"
        "            phase_label=\"议题\",\n"
        "            content=sess.topic,\n"
        "            badge=COLLAB_MODES[sess.collab_mode][\"label\"],\n"
        "            attachments=attachments,\n"
        "        )\n",
        "orchestrator.start_topic_chair_msg",
    )

    src = _replace_once(
        src,
        "            \"executor_agent\": sess.effective_executor_agent(),\n"
        "            \"can_rollback\": bool(sess.last_backup),\n"
        "        }\n",
        "            \"executor_agent\": sess.effective_executor_agent(),\n"
        "            \"can_rollback\": bool(sess.last_backup),\n"
        "            \"session_attachments\": merged_atts,\n"
        "        }\n",
        "orchestrator.start_topic_wb_atts",
    )

    # 6. chair_interrupt 接入补充上传的附件并合并至会话白板附件集
    src = _replace_once(
        src,
        "    async def chair_interrupt(self, sess: MeetingSession, message: str) -> None:\n"
        "        clean_msg = message.strip()\n"
        "        if not clean_msg:\n"
        "            return\n"
        "        was_busy = sess.is_busy\n"
        "        await self.cancel_active_flow(sess, reason_tag=\"主持人插话\" if was_busy else \"补充追问\")\n"
        "        if not sess.topic:\n"
        "            await self.start_topic_meeting(sess, clean_msg)\n"
        "            return\n\n"
        "        chair_msg = await self._append_non_agent_message(\n"
        "            sess,\n"
        "            speaker=\"chair\",\n"
        "            speaker_name=\"主持人\",\n"
        "            role_title=\"插话控场\" if was_busy else \"补充追问\",\n"
        "            phase_label=\"插话\" if was_busy else \"追问\",\n"
        "            content=clean_msg,\n"
        "            badge=\"新约束\" if was_busy else \"继续讨论\",\n"
        "        )\n",
        "    async def chair_interrupt(\n"
        "        self,\n"
        "        sess: MeetingSession,\n"
        "        message: str,\n"
        "        attachments: Optional[List[dict]] = None,\n"
        "    ) -> None:\n"
        "        clean_msg = message.strip()\n"
        "        if not clean_msg:\n"
        "            return\n"
        "        was_busy = sess.is_busy\n"
        "        await self.cancel_active_flow(sess, reason_tag=\"主持人插话\" if was_busy else \"补充追问\")\n"
        "        if not sess.topic:\n"
        "            await self.start_topic_meeting(sess, clean_msg, attachments=attachments)\n"
        "            return\n\n"
        "        if attachments:\n"
        "            cur_atts = list(sess.whiteboard.get(\"session_attachments\") or [])\n"
        "            seen_ids = {x.get(\"id\") for x in cur_atts if isinstance(x, dict)}\n"
        "            for att in attachments:\n"
        "                if isinstance(att, dict) and att.get(\"id\") and att[\"id\"] not in seen_ids:\n"
        "                    seen_ids.add(att[\"id\"])\n"
        "                    cur_atts.append(att)\n"
        "            sess.whiteboard[\"session_attachments\"] = cur_atts\n\n"
        "        chair_msg = await self._append_non_agent_message(\n"
        "            sess,\n"
        "            speaker=\"chair\",\n"
        "            speaker_name=\"主持人\",\n"
        "            role_title=\"插话控场\" if was_busy else \"补充追问\",\n"
        "            phase_label=\"插话\" if was_busy else \"追问\",\n"
        "            content=clean_msg,\n"
        "            badge=\"新约束\" if was_busy else \"继续讨论\",\n"
        "            attachments=attachments,\n"
        "        )\n",
        "orchestrator.chair_interrupt",
    )

    # 7. 导出 Markdown 纪要附带多模态附件索引摘要
    src = _replace_once(
        src,
        "        for c in wb.get(\"chair_constraints\") or []:\n"
        "            lines.append(f\"- [主持约束] {c}\")\n",
        "        for c in wb.get(\"chair_constraints\") or []:\n"
        "            lines.append(f\"- [主持约束] {c}\")\n"
        "        for att in wb.get(\"session_attachments\") or []:\n"
        "            if isinstance(att, dict) and att.get(\"name\"):\n"
        "                lines.append(f\"- [参考附件] {att['name']} ({att.get('size_human') or att.get('mime_type') or ''})\")\n",
        "orchestrator.export_attachments",
    )

    ast.parse(src, filename=str(orch_path))
    if src != orig:
        orch_path.write_text(src, encoding="utf-8")
        return True
    return False


def patch_cli_adapters(cli_path: Path) -> bool:
    orig = cli_path.read_text(encoding="utf-8")
    src = orig

    # 1. 导入 SessionAttachmentManager
    src = _replace_once(
        src,
        "from .workspace_backup import WorkspaceBackup\n",
        "from .attachments import SessionAttachmentManager\nfrom .workspace_backup import WorkspaceBackup\n",
        "cli_adapters.import_attachments",
    )

    # 2. WarmAntigravityProcess.stream_turn 支持将当前会话附件挂载至常驻进程专属 _call_tmp
    src = _replace_once(
        src,
        "    async def stream_turn(self, prompt: str) -> AsyncGenerator[dict, None]:\n"
        "        async with self._lock:\n"
        "            await self.ensure_started()\n"
        "            assert self.proc and self.proc.stdin and self.proc.stdout\n"
        "            payload = json.dumps({\"event\": \"user\", \"message\": {\"content\": prompt}}, ensure_ascii=False) + \"\\n\"\n",
        "    async def stream_turn(\n"
        "        self,\n"
        "        prompt: str,\n"
        "        *,\n"
        "        session_attachments: Optional[List[dict]] = None,\n"
        "        att_mgr: Optional[SessionAttachmentManager] = None,\n"
        "    ) -> AsyncGenerator[dict, None]:\n"
        "        async with self._lock:\n"
        "            await self.ensure_started()\n"
        "            assert self.proc and self.proc.stdin and self.proc.stdout\n"
        "            eff_prompt = prompt\n"
        "            if session_attachments and att_mgr is not None and self.session_id:\n"
        "                att_block, _ = att_mgr.stage_for_cli_turn(self.session_id, session_attachments, self._call_tmp)\n"
        "                if att_block:\n"
        "                    eff_prompt = f\"{att_block}\\n\\n{prompt}\"\n"
        "            payload = json.dumps({\"event\": \"user\", \"message\": {\"content\": eff_prompt}}, ensure_ascii=False) + \"\\n\"\n",
        "cli_adapters.warm_stream_turn",
    )

    # 3. UnifiedAgentRunner.__init__ 增加 self.attachments 与 _get_attachment_manager()
    src = _replace_once(
        src,
        "    def __init__(self, settings: RuntimeSettings):\n"
        "        self.settings = settings\n",
        "    def __init__(self, settings: RuntimeSettings):\n"
        "        self.settings = settings\n"
        "        self.attachments: Optional[SessionAttachmentManager] = None\n",
        "cli_adapters.runner_init",
    )

    src = _replace_once(
        src,
        "    def _get_binary_semaphore(self, binary_path: str, stateless_shared: bool = False) -> asyncio.Semaphore:\n",
        "    def _get_attachment_manager(self) -> SessionAttachmentManager:\n"
        "        if self.attachments is None:\n"
        "            self.attachments = SessionAttachmentManager()\n"
        "        return self.attachments\n\n"
        "    def _get_binary_semaphore(self, binary_path: str, stateless_shared: bool = False) -> asyncio.Semaphore:\n",
        "cli_adapters.get_attachment_manager",
    )

    # 4. stream_discussion_turn 透传 session_attachments 至 _stream_with_fallback
    src = _replace_once(
        src,
        "            stream_iter = self._stream_with_fallback(\n"
        "                session_id=session_id,\n"
        "                agent_id=agent_id,\n"
        "                driver_key=eff_drv,\n"
        "                model=eff_model,\n"
        "                effort=eff_effort,\n"
        "                binary_path=bpath,\n"
        "                help_text=help_text,\n"
        "                prompt=prompt,\n"
        "                use_warm=not use_stateless,\n"
        "                cwd_override=discuss_cwd,\n"
        "                discuss_readonly=True,\n"
        "                disable_stepdown_fallback=bool(ov and ov.get(\"strict_effort\")),\n"
        "            ).__aiter__()\n",
        "            sess_atts = whiteboard.get(\"session_attachments\") if isinstance(whiteboard, dict) else None\n"
        "            stream_iter = self._stream_with_fallback(\n"
        "                session_id=session_id,\n"
        "                agent_id=agent_id,\n"
        "                driver_key=eff_drv,\n"
        "                model=eff_model,\n"
        "                effort=eff_effort,\n"
        "                binary_path=bpath,\n"
        "                help_text=help_text,\n"
        "                prompt=prompt,\n"
        "                use_warm=not use_stateless,\n"
        "                cwd_override=discuss_cwd,\n"
        "                discuss_readonly=True,\n"
        "                disable_stepdown_fallback=bool(ov and ov.get(\"strict_effort\")),\n"
        "                session_attachments=sess_atts if isinstance(sess_atts, list) else None,\n"
        "            ).__aiter__()\n",
        "cli_adapters.discuss_pass_atts",
    )

    # 5. _stream_with_fallback 透传 session_attachments 至 _stream_raw_cli
    src = _replace_once(
        src,
        "        cwd_override: Optional[str] = None,\n"
        "        discuss_readonly: bool = True,\n"
        "        disable_stepdown_fallback: bool = False,\n"
        "    ) -> AsyncGenerator[dict, None]:\n",
        "        cwd_override: Optional[str] = None,\n"
        "        discuss_readonly: bool = True,\n"
        "        disable_stepdown_fallback: bool = False,\n"
        "        session_attachments: Optional[List[dict]] = None,\n"
        "    ) -> AsyncGenerator[dict, None]:\n",
        "cli_adapters.fallback_sig",
    )

    src = _replace_once(
        src,
        "                        prompt=prompt,\n"
        "                        use_warm=use_warm,\n"
        "                        cwd_override=cwd_override,\n"
        "                        discuss_readonly=discuss_readonly,\n"
        "                    ):\n",
        "                        prompt=prompt,\n"
        "                        use_warm=use_warm,\n"
        "                        cwd_override=cwd_override,\n"
        "                        discuss_readonly=discuss_readonly,\n"
        "                        session_attachments=session_attachments,\n"
        "                    ):\n",
        "cli_adapters.fallback_call_raw",
    )

    # 6. _stream_raw_cli 为 agy / grok / codex 统一挂载隔离 rt_attachments/ 目录与多模态提示块
    src = _replace_once(
        src,
        "        use_warm: bool = True,\n"
        "        cwd_override: Optional[str] = None,\n"
        "        discuss_readonly: bool = True,\n"
        "    ) -> AsyncGenerator[dict, None]:\n"
        "        cwd = cwd_override if (cwd_override and os.path.isdir(cwd_override)) else self._effective_workspace_cwd()\n"
        "        seat_key = (session_id, agent_id)\n\n"
        "        async def spawn_call(cmd, stdin):\n"
        "            env, call_tmp = self._prepare_isolated_call_env(session_id, agent_id)\n"
        "            try:\n"
        "                handle = await spawn_supervised_cli(cmd, cwd=cwd, env=env, stdin=stdin)\n"
        "                return handle, call_tmp\n"
        "            except BaseException:\n"
        "                self._cleanup_isolated_call_tmp(call_tmp)\n"
        "                raise\n",
        "        use_warm: bool = True,\n"
        "        cwd_override: Optional[str] = None,\n"
        "        discuss_readonly: bool = True,\n"
        "        session_attachments: Optional[List[dict]] = None,\n"
        "    ) -> AsyncGenerator[dict, None]:\n"
        "        cwd = cwd_override if (cwd_override and os.path.isdir(cwd_override)) else self._effective_workspace_cwd()\n"
        "        seat_key = (session_id, agent_id)\n"
        "        att_mgr = self._get_attachment_manager() if session_attachments else None\n\n"
        "        async def spawn_call_with_attachments(build_cmd_fn, stdin):\n"
        "            env, call_tmp = self._prepare_isolated_call_env(session_id, agent_id)\n"
        "            try:\n"
        "                staged_prompt = prompt\n"
        "                staged_imgs: List[str] = []\n"
        "                if session_attachments and att_mgr is not None:\n"
        "                    att_blk, staged_imgs = att_mgr.stage_for_cli_turn(session_id, session_attachments, call_tmp)\n"
        "                    if att_blk:\n"
        "                        staged_prompt = f\"{att_blk}\\n\\n{prompt}\"\n"
        "                final_cmd = build_cmd_fn(staged_prompt, staged_imgs)\n"
        "                handle = await spawn_supervised_cli(final_cmd, cwd=cwd, env=env, stdin=stdin)\n"
        "                return handle, call_tmp, staged_prompt\n"
        "            except BaseException:\n"
        "                self._cleanup_isolated_call_tmp(call_tmp)\n"
        "                raise\n",
        "cli_adapters.raw_spawn_helper",
    )

    # 6a. warm agy 调用传入 session_attachments
    src = _replace_once(
        src,
        "                try:\n"
        "                    async for ev in warm_inst.stream_turn(prompt):\n"
        "                        yield ev\n",
        "                try:\n"
        "                    async for ev in warm_inst.stream_turn(\n"
        "                        prompt,\n"
        "                        session_attachments=session_attachments,\n"
        "                        att_mgr=att_mgr,\n"
        "                    ):\n"
        "                        yield ev\n",
        "cli_adapters.raw_warm_agy",
    )

    # 6b. cold agy 调用挂载附件
    src = _replace_once(
        src,
        "            cmd = [binary_path, \"-p\", prompt]\n"
        "            if has_disable_slash:\n"
        "                cmd.append(\"--disable-slash-commands\")\n"
        "            if discuss_readonly and \"--sandbox\" in help_text:\n"
        "                cmd.append(\"--sandbox\")\n"
        "            if supports_stream_json:\n"
        "                cmd.extend([\"--output-format\", \"stream-json\"])\n"
        "            if model:\n"
        "                cmd.extend([\"--model\", model])\n"
        "            if has_effort and agy_effort:\n"
        "                cmd.extend([\"--effort\", agy_effort])\n\n"
        "            sup_handle, call_tmp_dir = await spawn_call(cmd, asyncio.subprocess.DEVNULL)\n",
        "            def _build_agy_cmd(eff_p: str, _imgs: List[str]) -> List[str]:\n"
        "                c = [binary_path, \"-p\", eff_p]\n"
        "                if has_disable_slash:\n"
        "                    c.append(\"--disable-slash-commands\")\n"
        "                if discuss_readonly and \"--sandbox\" in help_text:\n"
        "                    c.append(\"--sandbox\")\n"
        "                if supports_stream_json:\n"
        "                    c.extend([\"--output-format\", \"stream-json\"])\n"
        "                if model:\n"
        "                    c.extend([\"--model\", model])\n"
        "                if has_effort and agy_effort:\n"
        "                    c.extend([\"--effort\", agy_effort])\n"
        "                return c\n\n"
        "            sup_handle, call_tmp_dir, _ = await spawn_call_with_attachments(_build_agy_cmd, asyncio.subprocess.DEVNULL)\n",
        "cli_adapters.raw_cold_agy",
    )

    # Keep the Grok flags from the local release; only replace the prompt at argv[2].
    if "def _build_grok_cmd(" not in src:
        src = _replace_once(
            src,
            '            if "--permission-mode" in help_text:\n'
            '                cmd.extend(["--permission-mode", "dontAsk"])\n\n'
            '            sup_handle, call_tmp_dir = await spawn_call(cmd, asyncio.subprocess.DEVNULL)\n',
            '            if "--permission-mode" in help_text:\n'
            '                cmd.extend(["--permission-mode", "dontAsk"])\n\n'
            '            def _build_grok_cmd(eff_p: str, _imgs: List[str]) -> List[str]:\n'
            '                return [*cmd[:2], eff_p, *cmd[3:]]\n\n'
            '            sup_handle, call_tmp_dir, _ = await spawn_call_with_attachments(_build_grok_cmd, asyncio.subprocess.DEVNULL)\n',
            "cli_adapters.raw_grok",
        )

    # 6d. codex（及声明式外部驱动）挂载附件与 --image 多模态视觉参数
    src = _replace_once(
        src,
        "        cmd = [binary_path, \"exec\", \"--json\", \"--skip-git-repo-check\", \"--sandbox\", \"read-only\"]\n"
        "        if codex_eff in CANONICAL_EFFORT_LEVELS:\n"
        "            cmd.extend([\"-c\", f'model_reasoning_effort=\"{codex_eff}\"'])\n"
        "        if model:\n"
        "            cmd.extend([\"-m\", model])\n"
        "        if existing_tid:\n"
        "            cmd.extend([\"resume\", existing_tid, \"-\"])\n"
        "        else:\n"
        "            cmd.append(\"-\")\n\n"
        "        if driver_key != \"codex\" and DRIVER_SPECS.get(driver_key, {}).get(\"cmd_template\"):\n"
        "            tpl = DRIVER_SPECS[driver_key][\"cmd_template\"]\n"
        "            cmd = [\n"
        "                str(tok).format(binary=binary_path, model=model, effort=effort, prompt=prompt, cwd=cwd)\n"
        "                for tok in tpl\n"
        "            ]\n"
        "        sup_handle, call_tmp_dir = await spawn_call(cmd, asyncio.subprocess.PIPE)\n"
        "        proc = sup_handle.proc\n"
        "        self._register_raw_proc(seat_key, proc)\n"
        "        try:\n"
        "            assert proc.stdin is not None and proc.stdout is not None\n"
        "            proc.stdin.write(prompt.encode(\"utf-8\"))\n",
        "        def _build_codex_or_ext_cmd(eff_p: str, imgs: List[str]) -> List[str]:\n"
        "            if driver_key != \"codex\" and DRIVER_SPECS.get(driver_key, {}).get(\"cmd_template\"):\n"
        "                tpl = DRIVER_SPECS[driver_key][\"cmd_template\"]\n"
        "                return [\n"
        "                    str(tok).format(binary=binary_path, model=model, effort=effort, prompt=eff_p, cwd=cwd)\n"
        "                    for tok in tpl\n"
        "                ]\n"
        "            c = [binary_path, \"exec\", \"--json\", \"--skip-git-repo-check\", \"--sandbox\", \"read-only\"]\n"
        "            if codex_eff in CANONICAL_EFFORT_LEVELS:\n"
        "                c.extend([\"-c\", f'model_reasoning_effort=\"{codex_eff}\"'])\n"
        "            if model:\n"
        "                c.extend([\"-m\", model])\n"
        "            if existing_tid:\n"
        "                c.append(\"resume\")\n"
        "            if imgs and \"--image\" in help_text:\n"
        "                for img_p in imgs[-4:]:\n"
        "                    c.extend([\"--image\", img_p])\n"
        "                c.append(\"--\")\n"
        "            if existing_tid:\n"
        "                c.append(existing_tid)\n"
        "            c.append(\"-\")\n"
        "            return c\n\n"
        "        sup_handle, call_tmp_dir, eff_stdin_prompt = await spawn_call_with_attachments(\n"
        "            _build_codex_or_ext_cmd, asyncio.subprocess.PIPE\n"
        "        )\n"
        "        proc = sup_handle.proc\n"
        "        self._register_raw_proc(seat_key, proc)\n"
        "        try:\n"
        "            assert proc.stdin is not None and proc.stdout is not None\n"
        "            proc.stdin.write(eff_stdin_prompt.encode(\"utf-8\"))\n",
        "cli_adapters.raw_codex",
    )

    # 7. stream_agent_execution 为执行主刀席位同样挂载会话级图片与文件附件
    src = _replace_once(
        src,
        "                exec_env, exec_tmp = self._prepare_isolated_call_env(session_id or \"exec\", target_aid)\n"
        "                sup_handle = await spawn_supervised_cli(\n"
        "                    cmd,\n",
        "                exec_env, exec_tmp = self._prepare_isolated_call_env(session_id or \"exec\", target_aid)\n"
        "                exec_atts = whiteboard.get(\"session_attachments\") if isinstance(whiteboard, dict) else None\n"
        "                if exec_atts and session_id:\n"
        "                    att_b, _ = self._get_attachment_manager().stage_for_cli_turn(session_id, exec_atts, exec_tmp)\n"
        "                    if att_b and len(cmd) >= 3 and cmd[1] == \"-p\":\n"
        "                        cmd = list(cmd)\n"
        "                        cmd[2] = f\"{att_b}\\n\\n{exec_prompt}\"\n"
        "                sup_handle = await spawn_supervised_cli(\n"
        "                    cmd,\n",
        "cli_adapters.exec_agy_grok_atts",
    )

    src = _replace_once(
        src,
        "            exec_env, exec_tmp = self._prepare_isolated_call_env(session_id or \"exec\", target_aid)\n"
        "            sup_handle = await spawn_supervised_cli(\n"
        "                cmd,\n"
        "                cwd=cwd,\n"
        "                env=exec_env,\n"
        "                stdin=asyncio.subprocess.PIPE,\n"
        "                stdout=asyncio.subprocess.PIPE,\n"
        "                stderr=asyncio.subprocess.PIPE,\n"
        "                limit=4 * 1024 * 1024,\n"
        "                wait_release=bool(on_pgid_spawned is not None),\n"
        "            )\n"
        "            if on_pgid_spawned is not None:\n"
        "                await on_pgid_spawned(sup_handle.pgid)\n"
        "                sup_handle.release_gate()\n"
        "            proc = sup_handle.proc\n"
        "            seat_exec_key = (session_id or \"exec\", target_aid)\n"
        "            self._register_raw_proc(seat_exec_key, proc)\n"
        "            stderr_task = asyncio.create_task(_read_stderr_tail(proc.stderr))\n"
        "            exec_idle_sec = float(max(30, int(getattr(self.settings, \"idle_timeout_sec\", DEFAULT_IDLE_TIMEOUT_SEC) or DEFAULT_IDLE_TIMEOUT_SEC)))\n"
        "            exec_turn_sec = float(max(60, int(getattr(self.settings, \"turn_timeout_sec\", DEFAULT_TURN_TIMEOUT_SEC) or DEFAULT_TURN_TIMEOUT_SEC)))\n"
        "            exec_deadline = time.perf_counter() + exec_turn_sec\n"
        "            try:\n"
        "                assert proc.stdin is not None and proc.stdout is not None\n"
        "                proc.stdin.write(exec_prompt.encode(\"utf-8\"))\n",
        "            exec_env, exec_tmp = self._prepare_isolated_call_env(session_id or \"exec\", target_aid)\n"
        "            eff_codex_exec_prompt = exec_prompt\n"
        "            exec_atts = whiteboard.get(\"session_attachments\") if isinstance(whiteboard, dict) else None\n"
        "            if exec_atts and session_id:\n"
        "                att_b, exec_imgs = self._get_attachment_manager().stage_for_cli_turn(session_id, exec_atts, exec_tmp)\n"
        "                if att_b:\n"
        "                    eff_codex_exec_prompt = f\"{att_b}\\n\\n{exec_prompt}\"\n"
        "                if exec_imgs and \"--image\" in help_text:\n"
        "                    cmd = list(cmd[:-1])\n"
        "                    for img_p in exec_imgs[:4]:\n"
        "                        cmd.extend([\"--image\", img_p])\n"
        "                    cmd.append(\"-\")\n"
        "            sup_handle = await spawn_supervised_cli(\n"
        "                cmd,\n"
        "                cwd=cwd,\n"
        "                env=exec_env,\n"
        "                stdin=asyncio.subprocess.PIPE,\n"
        "                stdout=asyncio.subprocess.PIPE,\n"
        "                stderr=asyncio.subprocess.PIPE,\n"
        "                limit=4 * 1024 * 1024,\n"
        "                wait_release=bool(on_pgid_spawned is not None),\n"
        "            )\n"
        "            if on_pgid_spawned is not None:\n"
        "                await on_pgid_spawned(sup_handle.pgid)\n"
        "                sup_handle.release_gate()\n"
        "            proc = sup_handle.proc\n"
        "            seat_exec_key = (session_id or \"exec\", target_aid)\n"
        "            self._register_raw_proc(seat_exec_key, proc)\n"
        "            stderr_task = asyncio.create_task(_read_stderr_tail(proc.stderr))\n"
        "            exec_idle_sec = float(max(30, int(getattr(self.settings, \"idle_timeout_sec\", DEFAULT_IDLE_TIMEOUT_SEC) or DEFAULT_IDLE_TIMEOUT_SEC)))\n"
        "            exec_turn_sec = float(max(60, int(getattr(self.settings, \"turn_timeout_sec\", DEFAULT_TURN_TIMEOUT_SEC) or DEFAULT_TURN_TIMEOUT_SEC)))\n"
        "            exec_deadline = time.perf_counter() + exec_turn_sec\n"
        "            try:\n"
        "                assert proc.stdin is not None and proc.stdout is not None\n"
        "                proc.stdin.write(eff_codex_exec_prompt.encode(\"utf-8\"))\n",
        "cli_adapters.exec_codex_atts",
    )

    ast.parse(src, filename=str(cli_path))
    if src != orig:
        cli_path.write_text(src, encoding="utf-8")
        return True
    return False


def main() -> None:
    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    orch_file = repo_root / "backend" / "orchestrator.py"
    cli_file = repo_root / "backend" / "cli_adapters.py"
    att_file = repo_root / "backend" / "attachments.py"
    srv_file = repo_root / "backend" / "server.py"

    for req in (orch_file, cli_file, att_file, srv_file):
        if not req.is_file():
            raise SystemExit(f"[apply_v4_patches] 缺少关键后端源码文件: {req}")

    c1 = patch_orchestrator(orch_file)
    c2 = patch_cli_adapters(cli_file)
    for py_f in (att_file, srv_file, orch_file, cli_file):
        ast.parse(py_f.read_text(encoding="utf-8"), filename=str(py_f))

    print(
        f"[apply_v4_patches] AST 语法与多模态联动补丁校验通过 "
        f"(orchestrator={'patched' if c1 else 'up-to-date'}, cli_adapters={'patched' if c2 else 'up-to-date'})"
    )


if __name__ == "__main__":
    main()
