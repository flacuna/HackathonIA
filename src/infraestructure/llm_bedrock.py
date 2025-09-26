from __future__ import annotations

import json
import os
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

import boto3

from domain.models import ClusterSummary


class BedrockAnthropicClient:
    """Wrapper simples para chamar modelos Anthropic hospedados no AWS Bedrock.

    Espera variáveis de ambiente para configuração:
    - BEDROCK_REGION (ex: us-east-1)
    - BEDROCK_MODEL_ID (ex: anthropic.claude-3-5-sonnet-20240620-v1:0)
    - BEDROCK_TEMPERATURE (opcional, default 0.2)
    - BEDROCK_MAX_TOKENS (opcional, default 1200)
    - BEDROCK_STRUCTURED_OUTPUT (opcional, default "true")
    """

    def __init__(
        self,
        region_name: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        structured_output: Optional[bool] = None,
    ) -> None:
        self._region = region_name or os.getenv("BEDROCK_REGION", "us-east-1")
        self._model_id = model_id or os.getenv(
            "BEDROCK_MODEL_ID",
            # Sonnet 3.5 (2024-06-20) é amplamente suportado; usuário pode sobrescrever.
            "anthropic.claude-3-5-sonnet-20240620-v1:0",
        )
        self._temperature = (
            float(os.getenv("BEDROCK_TEMPERATURE", "0.2")) if temperature is None else float(temperature)
        )
        self._max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "1200")) if max_tokens is None else int(max_tokens)
        self._structured_output = (
            os.getenv("BEDROCK_STRUCTURED_OUTPUT", "true").lower() in {"1", "true", "yes"}
            if structured_output is None
            else bool(structured_output)
        )

        # Cria o cliente do runtime do Bedrock
        self._client = boto3.client("bedrock-runtime", region_name=self._region)
        self._debug = os.getenv("BEDROCK_DEBUG", "false").lower() in {"1", "true", "yes"}
        self._logger = logging.getLogger(__name__)

    def generate_structured_overview_pt(
        self,
        report_entries: Iterable[ClusterSummary],
        user_open_counts: Iterable[Tuple[str, int]] | None,
        daily_open_counts: Iterable[Tuple[str, int]] | None,
        data_inicio: Optional[str],
        data_fim: Optional[str],
    ) -> Dict[str, Any]:
        """Gera um resumo executivo estruturado (pt-BR) respeitando o range de datas.

        Retorna um dicionário com o seguinte formato:
        {
          "periodo": "YYYY-MM-DD a YYYY-MM-DD",
          "resumo_geral": "...",
          "sugestoes": ["...", "..."]
        }
        """
        entries_list: List[ClusterSummary] = list(report_entries)
        top_clusters = [
            {"grupo": e.group_name, "representante": e.representative_summary, "ocorrencias": e.occurrences}
            for e in entries_list[:10]
        ]
        top_usuarios = list((user_open_counts or []))[:10]
        serie_diaria = list((daily_open_counts or []))

        periodo = None
        if data_inicio and data_fim:
            periodo = f"{data_inicio} a {data_fim}"
        elif data_inicio:
            periodo = f"a partir de {data_inicio}"
        elif data_fim:
            periodo = f"até {data_fim}"
        else:
            periodo = "(sem intervalo definido)"

        user_content = self._build_prompt(top_clusters, top_usuarios, serie_diaria, periodo)

        base_body: Dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_content},
                    ],
                }
            ],
            "system": (
                "Você é um assistente especialista em operações de TI. Responda SEMPRE em português do Brasil. "
                "Produza um resumo objetivo e prático para liderança técnica e suporte."
            ),
        }

        # 1ª tentativa: com structured JSON (quando habilitado)
        body = dict(base_body)
        if self._structured_output:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "RelatorioResumoTickets",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "periodo": {"type": "string"},
                            "resumo_geral": {"type": "string"},
                            "sugestoes": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["periodo", "resumo_geral", "sugestoes"],
                    },
                    "strict": True,
                },
            }

        try:
            if self._debug:
                self._logger.info(
                    "Invocando Bedrock (model=%s, region=%s) com structured_output=%s",
                    self._model_id,
                    self._region,
                    self._structured_output,
                )

            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(body),
                accept="application/json",
                contentType="application/json",
            )
            # Body geralmente é um StreamingBody
            raw_body = response.get("body")
            if hasattr(raw_body, "read"):
                raw = raw_body.read()
            else:
                raw = raw_body if isinstance(raw_body, (bytes, bytearray)) else bytes(str(raw_body or "{}"), "utf-8")
            payload = json.loads(raw.decode("utf-8"))

            # Messages API (Anthropic) retorna topo com 'content': [{"type":"text","text":"..."}]
            content_list = payload.get("content")
            text = ""
            if isinstance(content_list, list) and content_list:
                first = content_list[0] or {}
                text = first.get("text", "")

            if self._structured_output and text:
                try:
                    data = json.loads(text)
                    if isinstance(data, dict) and data.get("periodo"):
                        return data
                except Exception:
                    pass
            # Fallback: tenta extrair JSON bruto do texto
            # Fallback: tenta extrair JSON do texto do conteúdo
            # Também cobre casos sem structured_output
            # Se text ainda não veio, tenta campos alternativos raros
            if not text:
                text = payload.get("completion") or ""
            data = self._best_effort_json(text)
            if data:
                return data
        except Exception as e:
            if self._debug:
                self._logger.exception("Falha ao invocar Bedrock (1ª tentativa): %s", e)

        # 2ª tentativa: sem response_format (texto livre), melhora compatibilidade
        try:
            response_2 = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(base_body),
                accept="application/json",
                contentType="application/json",
            )
            raw_body2 = response_2.get("body")
            if hasattr(raw_body2, "read"):
                raw2 = raw_body2.read()
            else:
                raw2 = raw_body2 if isinstance(raw_body2, (bytes, bytearray)) else bytes(str(raw_body2 or "{}"), "utf-8")
            payload2 = json.loads(raw2.decode("utf-8"))
            text2 = ""
            content_list2 = payload2.get("content")
            if isinstance(content_list2, list) and content_list2:
                text2 = (content_list2[0] or {}).get("text", "")
            if not text2:
                text2 = payload2.get("completion") or ""
            data2 = self._best_effort_json(text2)
            if data2:
                return data2
        except Exception as e:
            if self._debug:
                self._logger.exception("Falha ao invocar Bedrock (2ª tentativa): %s", e)

        return {
            "periodo": periodo,
            "resumo_geral": "Resumo automático indisponível no momento.",
            "sugestoes": [
                "Verificar conexões de rede e autenticação para os temas mais recorrentes.",
                "Padronizar playbooks de atendimento e criar FAQs para chamados repetitivos.",
            ],
        }

    @staticmethod
    def _build_prompt(
        top_clusters: List[Dict[str, Any]],
        top_usuarios: List[Tuple[str, int]],
        serie_diaria: List[Tuple[str, int]],
        periodo: str,
    ) -> str:
        def _fmt_clusters() -> str:
            lines = []
            for c in top_clusters:
                lines.append(
                    f"- {c['grupo']}: ocorrências={c['ocorrencias']} | representativo=\"{c['representante']}\""
                )
            return "\n".join(lines) if lines else "(sem dados)"

        def _fmt_users() -> str:
            lines = [f"- {u}: {n}" for u, n in top_usuarios]
            return "\n".join(lines) if lines else "(sem dados)"

        def _fmt_daily() -> str:
            lines = [f"- {d}: {n}" for d, n in serie_diaria]
            return "\n".join(lines) if lines else "(sem dados)"

        return (
            "Gere um RESUMO EXECUTIVO ESTRUTURADO em JSON sobre os tickets de suporte no período informado."\
            "\nRegras:"\
            "\n- Idioma: PT-BR."\
            "\n- Seja objetivo (3-6 frases no resumo)."\
            "\n- Traga insights sobre volume, possíveis causas e impactos."\
            "\n- Liste 3 a 6 sugestões práticas de mitigação/prevenção (ações concretas)."\
            "\n- Respeite o intervalo de datas informado ao comentar tendências."\
            "\n- Responda ESTRITAMENTE no esquema JSON com as chaves: periodo, resumo_geral, sugestoes."\
            f"\n\nPeríodo analisado: {periodo}"\
            f"\n\nTop grupos (até 10):\n{_fmt_clusters()}"\
            f"\n\nChamados por usuário (top 10):\n{_fmt_users()}"\
            f"\n\nChamados por dia (série):\n{_fmt_daily()}"\
        )

    @staticmethod
    def _best_effort_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        # Tenta encontrar o primeiro trecho JSON
        try:
            # Primeira tentativa: texto inteiro
            return json.loads(text)
        except Exception:
            pass
        # Heurística simples: procurar o primeiro e último colchete/chaves
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            pass
        return None
