"""Run the management agent against the configured model."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from model import ChatModelSettings, OpenAIChatModel

from .agent import ManageAgent
from .data_repository import BusinessDataRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="经营人员本次输入")
    parser.add_argument("--data-source-id", default="demo-acts-1-3")
    parser.add_argument("--data-root", type=Path, default=Path("data/scenarios"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser


async def _main() -> None:
    args = _parser().parse_args()
    settings = ChatModelSettings.from_env(args.env_file)
    model = OpenAIChatModel(settings)
    try:
        agent = ManageAgent(
            model=model,
            model_name=settings.model,
            repository=BusinessDataRepository(args.data_root),
        )
        result = await agent.run(
            data_source_id=args.data_source_id,
            user_message=args.message,
        )
        print(
            json.dumps(
                result.to_dict(include_trace=True),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    finally:
        await model.close()


if __name__ == "__main__":
    asyncio.run(_main())
