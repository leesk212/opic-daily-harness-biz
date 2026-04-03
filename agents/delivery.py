"""Delivery Agent - Slack으로 OPIC 문제 전송"""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID
from db import save_delivery, log_agent


class DeliveryAgent:
    name = "Delivery"

    def __init__(self):
        self.client = WebClient(token=SLACK_BOT_TOKEN)

    def _format_message(self, question_data: dict) -> list:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "OPIC Daily Practice",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Topic:* {question_data['topic']}  |  *Type:* {question_data['question_type']}  |  *Level:* AL",
                    }
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Question:*\n>{question_data['question']}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Key Expressions:*\n`{question_data.get('key_expressions', 'N/A')}`",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Tip:*\n{question_data.get('tip', '')}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Sample Answer (스포일러 주의! 먼저 직접 답해보세요):*",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{question_data.get('sample_answer', 'N/A')}```",
                },
            },
        ]
        return blocks

    async def send(self, question_data: dict) -> bool:
        await log_agent(self.name, "send", "started", f"question_id={question_data.get('id')}")

        try:
            blocks = self._format_message(question_data)
            response = self.client.chat_postMessage(
                channel=SLACK_CHANNEL_ID,
                text=f"OPIC Daily: {question_data['topic']} - {question_data['question_type']}",
                blocks=blocks,
            )

            await save_delivery(
                question_id=question_data.get("id"),
                slack_channel=SLACK_CHANNEL_ID,
                status="success",
            )
            await log_agent(self.name, "send", "success", f"ts={response['ts']}")
            return True

        except SlackApiError as e:
            error_msg = str(e.response["error"])
            await save_delivery(
                question_id=question_data.get("id"),
                slack_channel=SLACK_CHANNEL_ID,
                status="failed",
                error_message=error_msg,
            )
            await log_agent(self.name, "send", "failed", error_msg)
            return False

        except Exception as e:
            await save_delivery(
                question_id=question_data.get("id"),
                slack_channel=SLACK_CHANNEL_ID,
                status="failed",
                error_message=str(e),
            )
            await log_agent(self.name, "send", "failed", str(e))
            return False
