"""Native query conversion; imported only by the Core-backed adapter path."""
import logging
from typing import Any
from jiuwenswarm.agents.harness.code.prompt.plan_approval import (
    PLAN_EXECUTE_OPTION_VALUES,
    PLAN_REVISE_OPTION_VALUES,
    PLAN_SKIP_OPTION_VALUES,
    plan_skip_feedback,
)
from jiuwenswarm.agents.harness.common.rails.interrupt.contract import (
    EVOLUTION_INTERRUPT_METADATA_SOURCES,
)
from jiuwenswarm.agents.harness.common.rails.interrupt.permission_options import (
    ALLOW_ONCE,
    ALWAYS_ALLOW,
    REJECT,
    SESSION_ALLOW,
    is_keep_planning_value,
    normalize_option_value,
    resolve_permission_action,
)
from jiuwenswarm.common.config import get_config
from openjiuwen.core.session.interaction.interactive_input import InteractiveInput

logger = logging.getLogger(__name__)


def build_native_query(query, turn, params):
    if isinstance(query, InteractiveInput):
        final_query = query
    else:
        answers = params.get("answers", [])
        if answers:
            request_id = params.get("request_id", "")
            source = params.get("source", "")
            interactive_input = build_interactive_input_from_answers(
                request_id,
                answers,
                source,
            )
            if interactive_input is not None:
                final_query = interactive_input
                turn = turn.with_text(interactive_input)
            else:
                final_query = turn.render()
        else:
            final_query = turn.render()
            # 调试日志：确认 /statusline 是否已改写为内置子代理调度
            if isinstance(query, str) and "/statusline" in query:
                logger.info(
                    "[_build_inputs][STATUSLINE] 原始 query=%s, 最终 prompt 长度=%d, "
                    "包含 statusline-setup 调度=%s",
                    query[:200],
                    len(final_query) if isinstance(final_query, str) else 0,
                    "statusline-setup" in final_query if isinstance(final_query, str) else False,
                )
    return final_query, turn


def _permission_card_ids_from_answers(answers: list[dict]) -> list[str]:
    """Normalize the single opaque permission-card locator."""

    if len(answers) != 1:
        return []
    answer = answers[0]
    if not isinstance(answer, dict):
        return []
    raw_card_id = answer.get("card_id")
    if not isinstance(raw_card_id, str):
        return []
    card_id = raw_card_id.strip()
    if not card_id or len(card_id) > 128:
        return []
    return [card_id]


def _warn_unrecognised_approval_option(
    branch: str,
    source: Any,
    request_id: Any,
    value: Any,
    outcome: str,
) -> None:
    """审批选项没认出来时留一条告警，然后才按拒绝兜底。

    兜底成拒绝是对的：认不出来就不该放行。但在此之前它是静默的——用户点了同意，
    工具被拒，现场只剩一句用户看不到的 feedback，排查时无从下手。选项文案是跨端
    约定，任何一端改了字面量都会以"用户拒绝"的形式出现，因此这条告警要带上原始
    取值和落到哪个分支。

    取值为空是渲染端的"取消"（TUI 无拒绝项时按 Esc 即回传空串），属于正常路径，
    不是解析失败，不告警。
    """
    if not normalize_option_value(value):
        return
    logger.warning(
        "[JiuWenSwarm] %s unrecognised approval option: source=%s request_id=%s "
        "value=%r outcome=%s. The answer is refused because it could not be decoded, "
        "not because the user declined; check that the option vocabulary in "
        "permission_options matches what the channel sends.",
        branch,
        source,
        request_id,
        value,
        outcome,
    )


def build_interactive_input_from_answers(
        request_id: str,
        answers: list[dict],
        source: str = "",
) -> Any:
    """从用户答案构建 InteractiveInput.

    Args:
        request_id: 工具调用 ID
        answers: 用户答案列表，每个答案对应一个问题
        source: 中断来源，用于区分 PermissionRail 和 AskUserRail

    Returns:
        InteractiveInput 实例
    """
    from openjiuwen.core.session.interaction.interactive_input import (
        InteractiveInput,
    )

    interactive_input = InteractiveInput()

    if source == "ask_user_interrupt":
        answers_dict = {}
        free_text_answer: str | None = None
        for answer in answers:
            if isinstance(answer, dict):
                question_text = str(answer.get("question", "") or "").strip()
                selected_options = answer.get("selected_options", [])
                custom_input = str(answer.get("custom_input", "") or "").strip()
                if selected_options and isinstance(selected_options, list):
                    # Normalize each option to a stripped string, drop empties.
                    cleaned_options = [
                        str(raw_option or "").strip()
                        for raw_option in selected_options
                        if str(raw_option or "").strip()
                    ]
                    if custom_input:
                        # "Other" is only a UI placeholder. Preserve normal
                        # multi-select choices and append the user's text.
                        normal_options = [
                            option for option in cleaned_options if option != "Other"
                        ]
                        if normal_options:
                            answer_value: Any = [*normal_options, custom_input]
                        else:
                            answer_value = custom_input
                    elif len(cleaned_options) == 1:
                        # Bare "Other" without custom text is incomplete (#2330).
                        sole = cleaned_options[0]
                        answer_value = "" if sole == "Other" else sole
                    elif cleaned_options:
                        # Multi-select: preserve real choices; drop placeholder-only Other.
                        normal_options = [
                            option for option in cleaned_options if option != "Other"
                        ]
                        answer_value = normal_options if normal_options else ""
                    else:
                        answer_value = ""
                elif custom_input:
                    answer_value = custom_input
                else:
                    answer_value = ""
                if question_text and answer_value:
                    answers_dict[question_text] = answer_value
                elif answer_value:
                    free_text_answer = (
                        answer_value
                        if isinstance(answer_value, str)
                        else ", ".join(answer_value)
                    )
        if not answers_dict and free_text_answer:
            answers_dict["__free_text__"] = free_text_answer
        interactive_input.update(request_id, {"answers": answers_dict})
        logger.info(
            "[JiuWenSwarm] AskUserRail InteractiveInput.update: request_id=%s "
            "answer_count=%s",
            request_id,
            len(answers_dict),
        )
        return interactive_input

    if source in EVOLUTION_INTERRUPT_METADATA_SOURCES:
        answer = answers[0] if answers else {}
        selected_options = answer.get("selected_options", []) if isinstance(answer, dict) else []
        custom_input = answer.get("custom_input", "") if isinstance(answer, dict) else ""
        value = str(selected_options[0] if selected_options else "").strip()
        action_by_value = {
            "accept": "allow_once",
            "接收": "allow_once",
            "接受": "allow_once",
            "allow_once": "allow_once",
            "本次允许": "allow_once",
            "Allow Once": "allow_once",
            "allow_always": "allow_always",
            "总是允许": "allow_always",
            "Always Allow": "allow_always",
            "reject": "reject",
            "拒绝": "reject",
            "Reject": "reject",
        }
        action = action_by_value.get(value)
        if action is None:
            _warn_unrecognised_approval_option(
                "SkillEvolutionApproval", source, request_id, value, "rejected_as_unknown_option"
            )
            action = "reject"
        payload = {"action": action}
        if custom_input:
            payload["feedback"] = custom_input
        interactive_input.update(request_id, payload)
        logger.info(
            "[JiuWenSwarm] SkillEvolutionApproval InteractiveInput.update: request_id=%s payload=%s",
            request_id, payload
        )
        return interactive_input

    if source and source not in {
        "permission_interrupt",
        "confirm_interrupt",
    }:
        return None

    answer = answers[0] if answers else {}
    selected_options = answer.get("selected_options", []) if isinstance(answer, dict) else []
    custom_input = answer.get("custom_input", "") if isinstance(answer, dict) else ""

    value = selected_options[0] if selected_options else ""

    # 选项字符串来自各渲染端：web / CLI 回传 ``value``，TUI 回传 ``label``。
    # 统一走 ``permission_options`` 的词表解析，别在这里再维护一份字面量元组。
    action = resolve_permission_action(value)

    if action == ALLOW_ONCE:
        confirm_payload = {"approved": True, "auto_confirm": False, "feedback": ""}
    elif action == SESSION_ALLOW:
        confirm_payload = {
            "approved": True,
            "auto_confirm": True,
            "persist_allow": False,
            "feedback": "",
        }
    elif action == ALWAYS_ALLOW:
        confirm_payload = {
            "approved": True,
            "auto_confirm": True,
            "persist_allow": True,
            "feedback": "",
        }
    elif value in PLAN_EXECUTE_OPTION_VALUES:
        # Web 的"执行"：批准并退出 plan，但本轮不再调模型。真正的执行由前端
        # 紧接着补发的普通消息开启新一轮完成。``plan_execute`` 是额外键，
        # ConfirmPayload 会忽略它，rail 在校验前从原始 dict 读取。
        confirm_payload = {
            "approved": True,
            "auto_confirm": False,
            "feedback": "",
            "plan_execute": True,
        }
    elif value in PLAN_SKIP_OPTION_VALUES:
        # Web 的"跳过"：不退出 plan，也不继续修改，直接结束本轮。
        # ``plan_skip`` 是额外键，ConfirmPayload 会忽略它；
        # PlanApprovalInterruptRail 在校验前从原始 dict 读取该标记。
        confirm_payload = {
            "approved": False,
            "auto_confirm": False,
            "feedback": custom_input
            or plan_skip_feedback(get_config().get("preferred_language")),
            "plan_skip": True,
        }
    elif value in PLAN_REVISE_OPTION_VALUES:
        # Web 的"下一步"：不退出 plan，按修改意见续跑。``plan_revise`` 是额外键，
        # ConfirmPayload 会忽略它；rail 只在看到它时才给假回执包修订前缀。
        # TUI 仍发 ``reject``，不会进这个分支。
        confirm_payload = {
            "approved": False,
            "auto_confirm": False,
            "feedback": custom_input or "用户希望继续规划",
            "plan_revise": True,
        }
    elif action == REJECT:
        feedback = custom_input or (
            "用户希望继续规划" if is_keep_planning_value(value) else "用户拒绝"
        )
        confirm_payload = {"approved": False, "auto_confirm": False, "feedback": feedback}
    elif custom_input:
        # 选项没认出来，但用户填了自由文本，就用文本当反馈继续拒绝。取值仍然
        # 是没解出来的，同样要告警。
        _warn_unrecognised_approval_option(
            "PermissionRail", source, request_id, value, "rejected_with_custom_input"
        )
        confirm_payload = {"approved": False, "auto_confirm": False, "feedback": custom_input}
    else:
        _warn_unrecognised_approval_option(
            "PermissionRail", source, request_id, value, "rejected_as_unknown_option"
        )
        confirm_payload = {"approved": False, "auto_confirm": False, "feedback": f"未知选项: {value}"}

    card_ids = (
        _permission_card_ids_from_answers(answers)
        if source == "permission_interrupt" else []
    )
    if not card_ids:
        interactive_input.update(request_id, confirm_payload)
        return interactive_input
    interactive_input.update(card_ids[0], confirm_payload)
    logger.info(
        "[JiuWenSwarm] PermissionRail card InteractiveInput.update: "
        "request_id=%s card_id=%s",
        request_id,
        card_ids[0],
    )
    return interactive_input

