// fnIssue — builds one issue record. Severity/enablement come later from the
// VALIDATION_RULES table (joined in Issues), so rules stay data-driven.
(ruleId as text, documentName as text, sourceRow as nullable number, rowKey as nullable text, message as text) as record =>
[
    RuleId = ruleId,
    Document = documentName,
    SourceRow = sourceRow,
    RowKey = rowKey,
    Message = message
]
