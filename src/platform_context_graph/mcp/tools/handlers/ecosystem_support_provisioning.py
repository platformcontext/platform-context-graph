"""Provisioning-source helpers for deployment-chain summaries."""

from typing import Any


def group_provisioning_source_chains(
    *,
    terraform_modules: list[dict[str, Any]],
    terragrunt_configs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group service-relevant Terraform and Terragrunt sources by repo."""

    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def bucket(repository: str) -> dict[str, Any]:
        """Return the mutable grouping bucket for one provisioning repo."""

        if repository not in grouped:
            grouped[repository] = {
                "repository": repository,
                "terraform_modules": [],
                "terragrunt_configs": [],
            }
            order.append(repository)
        return grouped[repository]

    def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return rows with duplicates removed while preserving order."""

        seen: set[tuple[tuple[str, str], ...]] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    for row in terraform_modules:
        repository = str(row.get("repository") or "").strip()
        if not repository:
            continue
        bucket(repository)["terraform_modules"].append(
            {
                "name": row.get("name"),
                "source": row.get("source"),
                "version": row.get("version"),
                "source_repository": row.get("source_repository"),
            }
        )

    for row in terragrunt_configs:
        repository = str(row.get("repository") or "").strip()
        if not repository:
            continue
        bucket(repository)["terragrunt_configs"].append(
            {
                "name": row.get("name"),
                "terraform_source": row.get("terraform_source"),
                "file": row.get("file"),
                "source_repository": row.get("source_repository"),
            }
        )

    return [
        {
            "repository": repository,
            "terraform_modules": dedupe_rows(grouped[repository]["terraform_modules"]),
            "terragrunt_configs": dedupe_rows(
                grouped[repository]["terragrunt_configs"]
            ),
        }
        for repository in order
    ]
