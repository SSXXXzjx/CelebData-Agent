# -*- coding: utf-8 -*-
"""Celebrity CLI: lightweight agent over the dataset pipeline.

Surfaces:
  celebrity agent "task"     one-shot agent run (DeepSeek by default)
  celebrity chat             interactive multi-turn REPL
  celebrity pipeline --work  deterministic steps 5-8 over an existing dir
  celebrity deploy           deploy/check Spider_XHS
  celebrity doctor           environment/security diagnostics
  celebrity banner           render the banner
"""
import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__, banner, commands as slash, config as cfgmod, deploy, sessions, ui
from .core.agent import Agent, AgentError
from .providers import create_provider
from .providers.base import ProviderError
from .prompts import build_system_prompt
from .security import Redactor, mask_cookie
from .tools.base import ToolContext
from .tools.builtin import register_builtins
from .tools.registry import ToolRegistry
from .vision import create_vision, describe


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def build_ctx(cfg, allow_risk=None, confirm=None, interactive=False):
    redactor = Redactor(cfgmod.redaction_secrets(cfg))
    env = {}
    for key in ('XHS_COOKIE',):
        if os.environ.get(key):
            env[key] = os.environ[key]
    allowed = tuple(allow_risk) if allow_risk is not None else tuple(
        cfg.get('agent', {}).get('allow_risk', ['read']) or ['read'])
    ctx = ToolContext(
        cfg=cfg,
        work_dirs={k: str(v) for k, v in cfgmod.ensure_work_dirs(cfg).items()},
        redactor=redactor,
        vision=create_vision(cfg),
        confirm=confirm if interactive else None,
        allowed_risks=allowed,
        env=env,
    )
    return ctx


def build_agent(cfg, ctx):
    provider = create_provider(cfg)
    tools = ToolRegistry()
    register_builtins(tools)
    ctx.tool_names = tools.names
    agent = Agent(cfg, provider, tools, ctx, system_prompt=build_system_prompt(cfg))
    return agent, provider, tools


def _slash_command_map():
    """canonical command -> sorted aliases for the autocomplete dropdown."""
    cmds = {}
    for alias, name in slash.ALIASES.items():
        cmds.setdefault(name, set()).add(alias)
    for name in ('tools', 'reset', 'exit'):
        cmds.setdefault(name, set())
    return {name: sorted(aliases) for name, aliases in cmds.items()}


def _parse_risks(args):
    risks = {'read'}
    if getattr(args, 'allow_write', False):
        risks.add('write')
    if getattr(args, 'allow_destructive', False):
        risks.add('destructive')
    return tuple(sorted(risks))


def _confirm_exit():
    try:
        return ui.ask_confirm('确定要退出吗？', default=True)
    except KeyboardInterrupt:
        return True


def _progress_line(cfg, agent=None):
    """Pipeline progress rendered above the input frame."""
    parts = []
    latest = sessions.latest_work_dir(cfg)
    if latest is not None:
        raw, final = sessions.count_state(latest)
        parts.append(f'任务 {latest.name}')
        parts.append(f'raw {raw}')
        parts.append(f'final {final}')
    if agent is not None and agent.last_tool:
        parts.append(f'工具 {agent.last_tool}')
    return ' 进度 ' + (' │ '.join(parts) if parts else '暂无任务')


def _status_line(cfg, agent=None):
    """Model / token / elapsed metrics rendered below the input frame."""
    provider = cfgmod.get(cfg, 'provider.default', 'deepseek')
    model = cfgmod.get(cfg, f'provider.{provider}.model', '') or provider
    parts = [f'模型 {model}']
    if agent is not None:
        parts.append(f'Token {agent.usage["total_tokens"]}')
        parts.append(f'耗时 {agent.elapsed:.1f}s')
        parts.append(f'轮次 {agent.turn_count}')
    return ' ' + ' │ '.join(parts)


def render_main_page(cfg, agent=None):
    """Banner + welcome panel (features, commands, model)."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table

    banner.render('CELEBRITY', cfg)
    provider = cfgmod.get(cfg, 'provider.default', 'deepseek')
    model = cfgmod.get(cfg, f'provider.{provider}.model', '') or provider
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style='bold cyan', justify='right')
    table.add_column()
    table.add_row('功能', '爬取 → 去重 → 模型判断 → 打标签 → 打包')
    table.add_row('常用命令', '/model /vision /cookie /status /tools /help')
    table.add_row('操作提示', '输入 / 自动补全 · ESC/Ctrl+C 返回上一级')
    table.add_row('当前模型', f'[bold magenta]{model}[/bold magenta]（{provider}）')
    ui.console.print(Panel(table, title='✦ Welcome', border_style='cyan', expand=False))


def cmd_main(cfg, args):
    """Main page: banner + intro panel + menu. ESC/Ctrl+C here confirms exit."""
    state = {'agent': None}
    choices = ['进入对话', '环境诊断（doctor）', '退出']
    while True:
        if sys.stdin.isatty():
            ui.console.clear()
        render_main_page(cfg, state['agent'])
        try:
            idx, _ = ui.ask_choice('主菜单（↑/↓ 选择）', choices, default=1)
        except KeyboardInterrupt:
            if _confirm_exit():
                ui.info('再见')
                return 0
            continue
        if idx == 1:
            cmd_chat(cfg, args, state=state)
        elif idx == 2:
            cmd_doctor(cfg, args)
        else:
            if _confirm_exit():
                ui.info('再见')
                return 0


def cmd_agent(cfg, args):
    ctx = build_ctx(cfg, allow_risk=_parse_risks(args))
    agent, provider, tools = build_agent(cfg, ctx)
    ok, reason = provider.check()
    if not ok:
        ui.error(reason)
        ui.info('请在 .env 中配置密钥后重试（可先运行 celebrity doctor）')
        return 1
    ui.info(f'Provider: {reason} | 工具: {len(tools.names())} 个')
    try:
        handled, note = slash.try_store_credential(args.prompt, cfg, ctx)
        if handled:
            if note:
                ui.success(note)
            return 0
        result = _run_turn(agent, args.prompt, cfg)
    except AgentError as exc:
        ui.error(str(exc))
        return 1
    return 0


def _run_turn(agent, prompt, cfg):
    """Run one agent turn with Claude Code style streaming."""
    start = time.monotonic()
    tip = '└ Tip: 输入 / 可补全命令；粘贴密钥会自动保存到 .env' if agent.turn_count == 0 else None
    stream = ui.StreamUI(cfg, agent, start, tip=tip)
    try:
        result = agent.run(prompt, hooks=stream)
    except BaseException:
        stream.stop()
        raise
    ui.print_done(time.monotonic() - start)
    return result


def cmd_chat(cfg, args, state=None):
    cfg_path = getattr(args, 'config', None) or cfgmod.CONFIG_PATH
    if state is None:
        banner.render('CELEBRITY', cfg)
    elif sys.stdin.isatty():
        ui.console.clear()
    from prompt_toolkit.history import FileHistory
    history = FileHistory(str(cfgmod.ROOT / '.celebrity_history'))

    if state is not None and state.get('agent') is not None:
        # Re-enter chat: reuse the existing session so history is preserved.
        agent = state['agent']
        provider = agent.provider
        tools = agent.tools
        ctx = agent.ctx
    else:
        ctx = build_ctx(cfg, confirm=ui.ask_confirm, interactive=True)
        agent, provider, tools = build_agent(cfg, ctx)
        if state is not None:
            state['agent'] = agent
    ok, reason = provider.check()
    if not ok:
        ui.warn(reason)
    hints = '  Esc 返回主页面 · ↑↓ 历史 · / 补全'
    while True:
        try:
            text = ui.chat_input(
                _slash_command_map(),
                progress=_progress_line(cfg, agent),
                status=_status_line(cfg, agent),
                hints=hints,
                history=history,
            )
        except (EOFError, KeyboardInterrupt):
            print()
            ui.info('已返回主页面' if state is not None else '已退出')
            return
        s = text.strip()
        if not s:
            continue
        if s in ('/exit', '/quit', '/q'):
            break
        if s in ('/reset', '/new'):
            agent.reset()
            ui.info('已开启新会话')
            continue
        try:
            if s == '/tools':
                ui.table('可用工具', [[t] for t in tools.names()], headers=('工具',))
                continue
            if s.startswith('/'):
                try:
                    cfg, rebuild, stop = slash.run_slash(s, cfg, cfg_path)
                except KeyboardInterrupt:
                    ui.info('已取消设置，继续当前对话')
                    continue
                if stop:
                    break
                if rebuild:
                    ctx = build_ctx(cfg, confirm=ui.ask_confirm, interactive=True)
                    agent, provider, tools = build_agent(cfg, ctx)
                    if state is not None:
                        state['agent'] = agent
                    ui.success('配置已生效，会话已重置')
                continue
            handled, note = slash.try_store_credential(s, cfg, ctx)
            if handled:
                if note:
                    ui.success(note)
                continue
            _run_turn(agent, s, cfg)
        except KeyboardInterrupt:
            ui.info('已返回主页面' if state is not None else '已退出')
            return
        except AgentError as exc:
            ui.error(str(exc))


def cmd_pipeline(cfg, args):
    work_dir = Path(args.work).resolve() if args.work else sessions.latest_work_dir(cfg)
    if work_dir is None or not work_dir.is_dir():
        ui.error('未找到任务目录（用 --work 指定，或先运行 celebrity agent/chat 创建任务）')
        return 1
    vision = None
    if not args.skip_vision:
        from .vision.registry import resolve_vision
        try:
            if sys.stdin.isatty():
                vision = resolve_vision(
                    cfg,
                    confirm=ui.ask_confirm,
                    ask_choice=ui.ask_choice,
                    ask_text=ui.ask_text,
                )
            else:
                vision = create_vision(cfg)
                if vision is None or not vision.check()[0]:
                    raise RuntimeError(
                        '未配置可用的视觉模型；交互模式可选择下载或本地路径，'
                        '或加 --skip-vision 跳过判断')
        except RuntimeError as exc:
            ui.error(str(exc))
            return 1
    params = {}
    try:
        params = sessions.load_task(work_dir)
    except RuntimeError:
        pass
    celebrity = args.celebrity or params.get('celebrity') or 'celebrity'
    try:
        from .pipeline.runner import run_pipeline
        final_dir, zip_path, labels = run_pipeline(
            work_dir, cfg, vision if not args.skip_vision else None,
            celebrity=celebrity, caption_prompt=args.caption_prompt or '')
    except RuntimeError as exc:
        ui.error(str(exc))
        return 1
    return 0 if zip_path else 1


def cmd_deploy(cfg, args):
    deploy.deploy(cfg)
    return 0


def cmd_doctor(cfg, args):
    import importlib.util
    rows = []
    rows.append(('配置', str(args.config or cfgmod.CONFIG_PATH)))
    env_file = cfgmod.env_path()
    rows.append(('环境文件', str(env_file) + ('（已加载）' if env_file.exists() else '（缺失）')))
    provider = create_provider(cfg)
    ok, reason = provider.check()
    rows.append(('模型 Provider', ('可用: ' + reason) if ok else ('不可用: ' + reason)))
    vision = create_vision(cfg)
    rows.append(('视觉模型', describe(vision)))
    for mod, label in (
        ('PIL', 'Pillow'), ('numpy', 'numpy'), ('imagehash', 'imagehash'),
        ('cv2', 'opencv'), ('torch', 'torch/transformers'),
    ):
        rows.append((label, 'OK' if importlib.util.find_spec(mod) else '未安装（可选）'))
    spider = deploy.spider_dir(cfg)
    rows.append(('Spider_XHS', str(spider) + ('（存在）' if spider.is_dir() else '（缺失，运行 celebrity deploy）')))
    if spider.is_dir():
        for item in deploy.check_deps(spider):
            rows.append(('爬虫依赖', '缺失: ' + item))
    cookie = os.environ.get('XHS_COOKIE', '')
    rows.append(('小红书 Cookie', mask_cookie(cookie)))
    ui.table('celebrity doctor', rows, headers=('项目', '状态'))
    return 0


def cmd_banner(cfg, args):
    banner.render('CELEBRITY', cfg)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog='celebrity', description='轻量可扩展 agent：明星数据集构建')
    parser.add_argument('--config', default=None, help='配置文件路径（默认 config.yaml）')
    parser.add_argument('--version', action='store_true', help='显示版本')
    sub = parser.add_subparsers(dest='command')

    p_agent = sub.add_parser('agent', help='一次性 agent 任务（默认 DeepSeek）')
    p_agent.add_argument('prompt', help='任务描述，如：构建 宋雨琦 的数据集 500 张')
    p_agent.add_argument('--allow-write', action='store_true', help='允许写入型工具')
    p_agent.add_argument('--allow-destructive', action='store_true', help='允许破坏性工具（删除/覆盖）')
    p_agent.set_defaults(func=cmd_agent)

    p_chat = sub.add_parser('chat', help='交互式多轮对话')
    p_chat.set_defaults(func=cmd_chat)

    p_pipe = sub.add_parser('pipeline', help='对已有任务目录执行步骤 5-8')
    p_pipe.add_argument('--work', default='', help='任务目录（默认最近任务）')
    p_pipe.add_argument('--celebrity', default='', help='明星名称（用于 zip 文件名）')
    p_pipe.add_argument('--caption-prompt', default='', help='自定义 caption 提示词')
    p_pipe.add_argument('--skip-vision', action='store_true', help='跳过模型判断（全部放行）')
    p_pipe.set_defaults(func=cmd_pipeline)

    p_dep = sub.add_parser('deploy', help='部署/检查 Spider_XHS')
    p_dep.set_defaults(func=cmd_deploy)

    p_doc = sub.add_parser('doctor', help='环境与安全诊断')
    p_doc.set_defaults(func=cmd_doctor)

    p_banner = sub.add_parser('banner', help='渲染横幅')
    p_banner.set_defaults(func=cmd_banner)

    return parser.parse_args(argv)


def main(argv=None):
    _force_utf8()
    args = parse_args(argv)
    if args.version:
        print(f'Celebrity {__version__}')
        return 0
    cfgmod.load_env()
    cfg = cfgmod.load_config(args.config)
    cfgmod.ensure_work_dirs(cfg)
    if args.command is None:
        cmd_main(cfg, args)
        return 0
    try:
        return args.func(cfg, args) or 0
    except ProviderError as exc:
        ui.error(str(exc))
        return 1
    except KeyboardInterrupt:
        ui.warn('已取消')
        return 130
    except Exception as exc:
        ui.error(f'发生错误: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
