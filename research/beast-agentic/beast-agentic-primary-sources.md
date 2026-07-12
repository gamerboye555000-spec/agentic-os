# Beast Agentic Primary-Source Ledger

Research date: 2026-07-11

Purpose: evidence behind `AGENTIC_OS_BLUEPRINT.md`

Method: official specifications/documentation and original research papers were
preferred. Vendor claims are treated as implementation evidence, not neutral
proof. Emerging specifications and research prototypes are marked accordingly.

Recheck current versions, security advisories, licenses, and support status at
the start of the unit that adopts a dependency. A link in this ledger is not an
automatic adoption decision.

## 1. Local-first control and second-brain UX

| Source | What it supports | Maturity/use |
|---|---|---|
| [Local-first software: You own your data, in spite of the cloud](https://www.inkandswitch.com/essay/local-first/) | Offline use, user ownership, cross-device potential, long-term preservation, and CRDT tradeoffs | Foundational design paper; adopt principles |
| [Obsidian Bases](https://obsidian.md/help/bases) | Database-like filtered/table/card views derived from Markdown properties | Stable product surface; derived UX only |
| [Obsidian Canvas](https://obsidian.md/help/plugins/canvas) | Visual graph/canvas saved in the open JSON Canvas format | Stable product surface; derived UX only |
| [Automerge overview](https://automerge.org/docs/hello/) | CRDT-based automatic merging of concurrent offline changes | Mature library; defer until conflict semantics exist |
| [SQLite Online Backup API](https://sqlite.org/backup.html) | Consistent live database snapshot semantics | Mature; already reflected by U-C2 |

## 2. Tool and agent interoperability

| Source | What it supports | Maturity/use |
|---|---|---|
| [MCP specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) | Capability negotiation, client/host/server boundaries, tools/resources/prompts | Current stable line inspected; adopt later behind gateway |
| [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) | Typed tool descriptions and invocation | Stable concept; tool description remains untrusted |
| [MCP resources specification](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) | URI-addressed context resources and change notifications | Adopt lazy, authorized resource access |
| [MCP authorization tutorial](https://modelcontextprotocol.io/docs/tutorials/security/authorization) | OAuth-based protection of remote MCP resources | Required for remote MCP |
| [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices) | MCP-specific authorization attacks and mitigations | Required threat-model input |
| [A2A v1 specification](https://a2a-protocol.org/latest/specification/) | Cross-framework agent messages, tasks, artifacts, authentication and lifecycle | v1 standard; boundary adapter candidate |
| [A2A Agent Discovery](https://a2a-protocol.org/latest/topics/agent-discovery/) | Agent Cards, capability/skill discovery, caching | Discovery only; card is not trust |
| [A2A life of a task](https://a2a-protocol.org/latest/topics/life-of-a-task/) | Long-running task, input-required and terminal-state semantics | Map to Beast workflow/interrupt states |
| [A2A protocol definitions](https://a2a-protocol.org/latest/definitions/) | Normative protobuf and generated JSON representation | Use for compatibility tests if adopted |

## 3. Agent orchestration and human control

| Source | What it supports | Maturity/use |
|---|---|---|
| [OpenAI Agents SDK: multi-agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/) | Manager-as-tools versus handoff patterns | Framework adapter candidate; adopt concepts |
| [OpenAI Agents SDK: human in the loop](https://openai.github.io/openai-agents-python/human_in_the_loop/) | Serializable pause/approve/reject/resume around sensitive tool calls | Strong reference for HITL contracts |
| [OpenAI Agents SDK: guardrails](https://openai.github.io/openai-agents-python/guardrails/) | Input/output/tool guardrails and scope limitations | Useful; note handoff/tool guardrail boundary |
| [OpenAI Agents SDK: tracing](https://openai.github.io/openai-agents-python/tracing/) | Tracing model generations, tools, handoffs, guardrails and custom events | Adapter signal; Beast keeps vendor-neutral trace spine |
| [AutoGen AgentChat](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/index.html) | High-level agents and predefined team patterns | Framework adapter/research candidate |
| [AutoGen teams](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html) | Team presets and observable multi-agent control | Compare in task-specific benchmarks |
| [AutoGen multi-agent application concepts](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/core-concepts/agent-and-multi-agent-application.html) | Cross-process, cross-machine and cross-language agents communicating by messages | Supports a framework-neutral envelope |
| [Should we be going MAD?](https://arxiv.org/abs/2311.17371) | Multi-agent debate accuracy/cost/latency tradeoffs | Research; supports capped, evaluated debate only |
| [AgentGroupChat-V2](https://arxiv.org/abs/2506.15451) | Reported degradation as agent count increases in studied settings | Research warning against “more agents is better” |

## 4. Durable workflows, loops, and interrupts

| Source | What it supports | Maturity/use |
|---|---|---|
| [Temporal workflow execution](https://docs.temporal.io/workflow-execution) | Durable workflow functions and persisted execution history | Mature pattern/engine candidate |
| [Temporal workflow message passing](https://docs.temporal.io/handling-messages) | Signals, Updates, Queries, atomicity and idempotency concerns | Reference for Semantic Interrupt Kernel |
| [Temporal deterministic workflow definition](https://docs.temporal.io/workflow-definition) | Replay determinism and workflow versioning constraints | Required if Temporal is adopted |
| [Temporal safe deployments](https://docs.temporal.io/develop/safe-deployments) | Versioning/patching running workflows | Required operational gate |
| [Temporal Continue-As-New](https://docs.temporal.io/workflow-execution/continue-as-new) | Fresh event history carrying forward relevant state | Useful for long-running context/history control |
| [Temporal multi-cluster replication](https://docs.temporal.io/temporal-service/multi-cluster-replication) | Active/passive workflow replication and failover | Marked experimental; not initial DR basis |
| [Open Workflow Specification](https://serverlessworkflow.io/) | Vendor-neutral JSON/YAML workflow DSL and schemas | Adopt ideas; avoid full complexity in v1 IR |
| [W3C SCXML](https://www.w3.org/TR/scxml/) | Event-based state-machine semantics including parallel states | Mature reference for lifecycle semantics |

## 5. Events, tracing, and cross-boundary context

| Source | What it supports | Maturity/use |
|---|---|---|
| [CloudEvents](https://cloudevents.io/) | Portable common event envelope across systems | CNCF standard; adopt event-shape concepts |
| [W3C Trace Context](https://www.w3.org/TR/trace-context/) | Standard trace propagation across services | W3C Recommendation; adopt |
| [W3C Baggage](https://www.w3.org/TR/baggage/) | Propagation of application-defined context | Adopt cautiously; no sensitive data |
| [OpenTelemetry specification](https://opentelemetry.io/docs/specs/otel/) | Vendor-neutral traces, metrics, logs and context APIs | Adopt telemetry contract |
| [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/) | Common attribute names across telemetry | Adopt where stable; version conventions |
| [OpenTelemetry messaging spans](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/) | Propagating creation context through asynchronous messages | Supports queue/result trace continuity |

## 6. Memory and context engineering

| Source | What it supports | Maturity/use |
|---|---|---|
| [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) | OS-inspired memory tiers, virtual context and interrupts | Foundational research inspiration |
| [Letta memory blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks/) | Pinned persistent memory always visible in context | Product reference; adopt tiering concept |
| [Letta archival memory](https://docs.letta.com/guides/core-concepts/memory/archival-memory/) | Searchable long-term memory loaded on demand | Product reference; adopt lazy retrieval concept |
| [Letta shared memory](https://docs.letta.com/guides/core-concepts/memory/shared-memory/) | Multiple agents sharing memory blocks | Demonstrates value and poisoning/race risk |
| [Graphiti overview](https://help.getzep.com/graphiti/getting-started/overview) | Evolving temporal knowledge graph of entities, relationships and facts | Derived-index prototype candidate |
| [Graphiti facts](https://help.getzep.com/facts) | `valid_at`/`invalid_at` temporal fact semantics | Supports time-valid claim fields |
| [MIRIX multi-agent memory](https://arxiv.org/abs/2507.07957) | Core, episodic, semantic, procedural, resource and vault memory types | Research inspiration; independently validate |
| [Temporal Semantic Memory](https://arxiv.org/abs/2601.07468) | Episodic temporal graph plus consolidated durative memory | Recent research; inspiration for consolidation |
| [A-Mem](https://arxiv.org/abs/2502.12110) | Dynamic linked notes inspired by Zettelkasten | Research inspiration; watch cost/error accumulation |
| [Lost in the Middle](https://arxiv.org/abs/2307.03172) | Long context can miss relevant information depending on position | Strong reason for retrieval/sharding/evals |
| [MCP resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) | Lazily addressable external context by URI | Standards-based resource handles |

## 7. Typed and neural-symbolic boundaries

| Source | What it supports | Maturity/use |
|---|---|---|
| [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | Versioned structural validation, references and vocabularies | Adopt for envelopes/manifests |
| [JSON Schema core specification](https://json-schema.org/draft/2020-12/json-schema-core) | Data model, schema identity and validation mechanisms | Normative basis |
| [Open Policy Agent](https://openpolicyagent.org/docs) | Separating policy decision from enforcement over structured input | Adopt after simple policy kernel |
| [OPA policy language](https://openpolicyagent.org/docs/policy-language) | Rego/Datalog-inspired assertions over JSON-like data | Policy-as-code candidate |
| [OPA decision logs](https://openpolicyagent.org/docs/management-decision-logs) | Auditable policy query inputs and bundle metadata | Map to privacy-safe Beast decisions |
| [Z3 Guide](https://microsoft.github.io/z3guide/) | SMT modeling and satisfiability/constraint solving | Trigger-gated for complex constraints |

## 8. Model routing, cascades, optimization, and distillation

| Source | What it supports | Maturity/use |
|---|---|---|
| [RouteLLM](https://arxiv.org/abs/2406.18665) | Learned strong/weak model routing using preference data | Research/code; use after labels and shadow |
| [RouterBench](https://arxiv.org/abs/2403.12031) | Standardized multi-LLM router evaluation with large outcome dataset | Benchmark inspiration |
| [FrugalGPT](https://arxiv.org/abs/2305.05176) | Cascades balancing model cost and quality | Adopt cascade/eval ideas, not reported gains blindly |
| [DSPy paper](https://arxiv.org/abs/2310.03714) | Declarative model programs optimized against metrics | Offline Strategy Foundry candidate |
| [DSPy documentation](https://dspy.ai/) | Current program/signature/optimizer implementation | Dependency candidate for experiments only |
| [OPRO](https://arxiv.org/abs/2309.03409) | LLM-generated candidates optimized from prior scored solutions | Offline prompt optimization inspiration |
| [TextGrad](https://arxiv.org/abs/2406.07496) | Textual feedback propagated through compound AI systems | Experimental optimizer; requires independent verification |
| [Distilling Step-by-Step](https://arxiv.org/abs/2305.02301) | Rationales/labels as extra supervision for smaller task models | Research basis; licensing/privacy gate required |

## 9. Factuality, hallucination, and retrieval evaluation

| Source | What it supports | Maturity/use |
|---|---|---|
| [FActScore](https://arxiv.org/abs/2305.14251) | Decomposing long output into atomic facts and checking source support | Adopt pattern with calibrated graders |
| [SAFE / Long-form factuality](https://arxiv.org/abs/2403.18802) | Search-augmented atomic fact verification | Research reference; search is also untrusted |
| [RAGAS](https://arxiv.org/abs/2309.15217) | Retrieval/generation metrics such as faithfulness and relevance | Use as eval inspiration, not sole release gate |

## 10. Security, identity, sandbox, and supply chain

| Source | What it supports | Maturity/use |
|---|---|---|
| [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) | Govern/map/measure/manage AI risk lifecycle | Adopt risk-governance framing |
| [NIST Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence) | GenAI-specific risk considerations and actions | Threat/control checklist input |
| [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) | Current agentic threat categories and mitigations | Primary community security reference |
| [OWASP LLM Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) | Direct/indirect prompt injection risk | Required adversarial suite |
| [SPIFFE overview](https://spiffe.io/docs/latest/spiffe-about/overview/) | Platform-neutral short-lived workload identities | Production multi-service identity candidate |
| [SPIFFE federation](https://spiffe.io/docs/latest/spiffe-specs/spiffe_federation/) | Trust-domain federation across environments | Cross-cloud identity candidate |
| [Landlock](https://docs.kernel.org/userspace-api/landlock.html) | Unprivileged restriction of filesystem/network ambient rights | Local Linux sandbox layer |
| [gVisor architecture](https://gvisor.dev/docs/architecture_guide/intro/) | Application-kernel isolation for untrusted workloads | Runtime OCI sandbox candidate |
| [Linux seccomp filter documentation](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html) | Reducing kernel syscall attack surface; explicitly not a complete sandbox | Defense-in-depth only |
| [SLSA v1.2 specification](https://slsa.dev/spec/v1.2/) | Build provenance and isolation requirements | Release supply-chain target |
| [Sigstore Cosign signing overview](https://docs.sigstore.dev/cosign/signing/overview/) | Ephemeral-key signing and transparency-log evidence | Release/image signing candidate |
| [GitHub CodeQL code scanning](https://docs.github.com/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql) | Static security analysis integrated with GitHub | Adopt for supported code |
| [GitHub secret scanning](https://docs.github.com/code-security/secret-scanning/about-secret-scanning) | Repository/history credential detection | Enable plus local U-C3 defense |
| [OpenSSF Scorecard](https://openssf.org/projects/scorecard/) | Automated open-source project security checks | Supply-chain health signal |
| [OSS-Fuzz](https://google.github.io/oss-fuzz/) | Continuous coverage-guided fuzzing | Use where language/attack surface justify it |

## 11. Reliability, networking, and cross-cloud

| Source | What it supports | Maturity/use |
|---|---|---|
| [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking) | Retry budgets and protection against cascading retry load | Adopt concepts at gateway/runtime |
| [Envoy outlier detection](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/outlier) | Removing unhealthy endpoints from load balancing | Provider/service mesh reference |
| [Kubernetes multiple zones](https://kubernetes.io/docs/setup/best-practices/multiple-zones/) | Multi-zone control/workload placement | Production single-region baseline |
| [Kubernetes Multicluster Services API](https://multicluster.sigs.k8s.io/concepts/multicluster-services-api/) | Service export/import across clusters | API concept; no reference implementation claimed |
| [PostgreSQL high availability](https://www.postgresql.org/docs/current/high-availability.html) | HA, standby, replication and load-balancing options | Runtime database basis |
| [PostgreSQL logical replication failover](https://www.postgresql.org/docs/current/logical-replication-failover.html) | Replication-slot readiness across failover | Advanced DR reference; managed service specifics vary |
| [Temporal self-hosted multi-cluster replication](https://docs.temporal.io/self-hosted-guide/multi-cluster-replication) | Duplicate dispatch/progress rollback concerns under async failover | Evidence for idempotency and active/passive caution |

## 12. Economic negotiation and serendipity

| Source | What it supports | Maturity/use |
|---|---|---|
| [Agent Payments Protocol](https://ap2-protocol.org/) | Verifiable user mandates and interoperable agent-led payment model | Emerging v0.x protocol; late sandbox only |
| [AP2 reference repository](https://github.com/google-agentic-commerce/AP2) | Specification, SDK and sample scenarios | Inspect/pin only during U-Q5 |
| [A2A Agent Skills and Card](https://a2a-protocol.org/latest/tutorials/python/3-agent-skills-and-card/) | Capability descriptions for discovery | Input to internal directory; not proof |
| [MMR for diversity](https://aclanthology.org/X98-1025/) | Balancing relevance and redundancy/diversity | Mature ranking idea for retrieval/serendipity |
| [Fluid Transformers and Creative Analogies](https://arxiv.org/abs/2302.12832) | Potential and risks of cross-domain LLM analogies | Research basis for opt-in, skeptic-gated ideas |
| [Beyond-Accuracy recommender review](https://arxiv.org/abs/2310.02294) | Diversity, novelty, serendipity and fairness beyond accuracy | Evaluation inspiration |

## 13. GitHub delivery controls

| Source | What it supports | Maturity/use |
|---|---|---|
| [Secure use of GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use) | Least privilege, pinning, untrusted input and workflow security | Required for U-P1/runtime CI hardening |
| [Building and testing Python](https://docs.github.com/actions/guides/building-and-testing-python) | Supported Python CI setup | Reference for test matrix |
| [GitHub deployment environments](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) | Required reviewers, wait timers, branch restrictions and secrets after approval | Production deployment gate |

## 14. Research conclusions carried into the blueprint

1. Long context is not reliable memory; retrieval, temporal filtering, token
   budgets, provenance and context-use evaluation are required.
2. Agent descriptions and protocol cards enable discovery but do not establish
   identity, fitness, policy authority, or safety.
3. Durable workflows require deterministic replay/version discipline and every
   external side effect must be idempotent or compensatable.
4. Multi-agent systems can improve some tasks but added agents introduce cost,
   latency and coordination failure; topology must be task-evaluated.
5. Learned routing, automatic prompt optimization and distillation are data and
   eval problems, not configuration toggles.
6. Automated factuality graders are useful only with atomic claims, sources,
   grader versioning and human calibration.
7. Security requires identity, authorization, data controls, tool enforcement,
   sandboxing, supply-chain integrity, monitoring and recovery; prompt filters
   alone are insufficient.
8. Multi-cloud failover changes delivery semantics. Assume duplicates and lag,
   then design fencing, reservations, idempotency and compensation.
9. Agent payments and autonomous markets are emerging. Internal simulation and
   verifiable mandates must precede real money.
10. The current Beast Agentic build should continue at U-C3; research does not
    justify skipping the canonical reliability spine.
