# Data folder

- chroma_db/: Persistência local do banco vetorial (ChromaDB). Pode ser sobrescrito via env `CHROMA_DB_PATH`.
- JIRA_limpo.csv: Export do Jira usado para enriquecer relatórios. Pode ser sobrescrito via env `JIRA_CSV_PATH`.

Observações:
- Em produção, prefira montar volumes ou apontar `CHROMA_DB_PATH` e `JIRA_CSV_PATH` via variáveis de ambiente.
- Evite comitar o conteúdo de `chroma_db/` (binários). O CSV pode ser grande; avalie se deve ser versionado.
