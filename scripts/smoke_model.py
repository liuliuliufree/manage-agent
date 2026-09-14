"""Run one minimal request against the configured model endpoint."""

import asyncio

from model import ChatModelSettings, OpenAIChatModel


async def main() -> None:
    settings = ChatModelSettings.from_env()
    model = OpenAIChatModel(settings)
    try:
        completion = await model.complete(
            {
                "model": settings.model,
                "messages": [
                    {
                        "role": "user",
                        "content": "只回复一个英文单词：Success",
                    }
                ],
            }
        )
        message = completion.choices[0].message.content
        if not message:
            raise RuntimeError("Model returned an empty text response")
        print(message)
    finally:
        await model.close()


if __name__ == "__main__":
    asyncio.run(main())
