"""Run the acts 1-3 Agent against the configured OpenAI-compatible model."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from model import ChatModelSettings, OpenAIChatModel

from .repository import ScenarioRepository
from .workflow import ActsOneToThreeAgent


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="经营人员本次输入")
    parser.add_argument("--scenario-id", default="demo-acts-1-3")
    parser.add_argument("--opportunity-id")
    parser.add_argument("--scenarios-root", type=Path, default=Path("data/scenarios"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser


async def _main() -> None:
    args = _parser().parse_args()
    settings = ChatModelSettings.from_env(args.env_file)
    model = OpenAIChatModel(settings)
    try:
        agent = ActsOneToThreeAgent(
            model=model,
            model_name=settings.model,
            repository=ScenarioRepository(args.scenarios_root),
        )
        result = await agent.run(
            scenario_id=args.scenario_id,
            user_message=args.message,
            selected_opportunity_id=args.opportunity_id,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    finally:
        await model.close()


if __name__ == "__main__":
    asyncio.run(_main())
