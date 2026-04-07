# Security and Responsible Use

Are-Self is an MIT-licensed, open-source AI orchestration framework designed to run entirely on consumer hardware. This document outlines its security properties, dual-use considerations, and the responsibilities that come with deploying an autonomous reasoning system.

## Privacy & Data Sovereignty

**Are-Self is built with privacy-first architecture by default.**

- All data is stored and processed locally on the operator's machines
- No telemetry collection, no phone-home functionality, no mandatory cloud dependency
- Long-term memories, tool execution logs, and session state live in PostgreSQL with pgvector on the operator's hardware
- The system does not transmit operational data to external services unless explicitly configured to do so

### Cloud Failover (Optional)

Are-Self supports optional cloud failover through OpenRouter for LLM inference. This is:

- **Opt-in**: Disabled by default. Cloud fallback requires explicit configuration.
- **Clearly configurable**: When enabled, it's transparent which models route to cloud and which remain local
- **Not required**: You can run the entire system using only local Ollama models without any cloud integration

### Regulatory Alignment

This local-by-default architecture has built-in alignment with:

- **HIPAA**: Protected Health Information never leaves the local network unless explicitly transmitted by the operator. No cloud-dependent services means PHI storage and processing can be entirely contained on regulated infrastructure.
- **SOC 2 Type I**: Local-only operation eliminates cloud provider dependencies and most third-party risk vectors. Access controls, audit logging, and encryption at rest (via PostgreSQL) are achievable at the operator level.
- **GDPR**: Are-Self itself collects no personal data. What you put into it stays where you put it.

**Compliance caveat**: Full compliance is operator-dependent. The framework provides the foundation, but you must implement access controls, backup procedures, network security, and audit procedures appropriate for your regulatory context.

## Dual-Use Acknowledgment

**Are-Self is a powerful autonomous system. We will not pretend otherwise.**

This framework gives AI entities the ability to:

- Form long-term memories and build context over time
- Execute tools and interact with external systems
- Manage their own work and adapt behavior
- Scale across multiple machines via the Peripheral Nervous System (swarm)
- Reason about tasks and solve problems with minimal human intervention

The same capabilities that enable beneficial use cases—logistics automation for nonprofits, research workflows, personalized healthcare applications—can be misused for:

- Coordinated automated scraping at scale
- Resource exhaustion attacks or distributed request flooding
- Unauthorized data harvesting from open endpoints
- Manipulation or spam campaigns at machine speed and scale

**This is not unique to Are-Self.** Any sufficiently capable automation framework has dual-use potential. What distinguishes Are-Self is that we acknowledge it directly rather than pretending the risk doesn't exist.

### What the Operator Controls

Dual-use risk is directly tied to **what tools you give the system**. Are-Self does not ship with dangerous capabilities. The Parietal Lobe gateway defines what the system can do. If you configure tools that can:

- Make unlimited HTTP requests to external systems
- Scrape or crawl the web
- Interact with APIs without rate-limiting
- Execute arbitrary code or shell commands
- Access cloud infrastructure with elevated privileges

...then you are creating the potential for misuse. The framework provides guardrails, but the tool set is your choice.

## Architectural Safeguards

Are-Self includes multiple layers of built-in constraints:

### Focus Economy

The Focus Economy limits how much work any single session can execute before enforcing a mandatory rest period. This prevents runaway execution loops and gives operators visibility into system behavior.

### Parietal Lobe Gateway

Tool execution is gated through the Parietal Lobe with:

- **Hallucination armor**: Parameter validation to prevent tools from executing with invalid, malicious, or nonsensical inputs
- **Granular authorization**: Each tool has defined inputs, outputs, and constraints
- **Execution logging**: Every tool invocation is recorded for audit and forensics

### Hypothalamus Budget Enforcement

Model usage is constrained by:

- Token budgets per session
- Rate limiting on inference calls
- Hard stops when budgets are exceeded (no silent failures, no opportunistic overages)

### Circuit Breakers

Failing endpoints do not get hammered indefinitely:

- Failed tool calls trigger exponential backoff
- Repeated failures cause the tool to be disabled for the session
- The system recovers gracefully without cascading failures

### Spike Forensics

All execution is auditable:

- Every action leaves a trace in the audit log
- Session state, tool invocations, and decision points are recorded
- You can replay, inspect, and understand exactly what the system did and why

### Planned: Tool Approval Gates

A permission model similar to Claude's is planned where tools that make network requests, access external APIs, or execute code require human confirmation before execution. This will shift the burden of denial-of-service risk even further toward operator control.

## Operator Responsibility

**MIT license means you own the consequences of how you deploy Are-Self.**

### Configuration Matters

The Parietal Lobe tools you configure determine what the system can do:

- If you give it unrestricted web access, it can crawl at scale
- If you connect it to a cloud API with high-rate-limit tolerance, it can hammer that API
- If you give it network access to internal systems, it can interact with internal systems
- If you give it database access, it's your responsibility to set appropriate row-level and column-level permissions

### Network-Facing Deployments

If you expose Are-Self over a network:

- Use standard authentication and authorization controls (API keys, OAuth, mutual TLS)
- Place the system behind a firewall with appropriate ingress/egress rules
- Rate-limit incoming requests at the network level
- Use network segmentation to isolate the system from critical infrastructure
- Monitor for unexpected tool execution or data access patterns

These are standard practices for any API-serving application. Are-Self is no exception.

### Peripheral Nervous System (Swarm) Security

The Peripheral Nervous System allows Are-Self agents to scale across multiple machines. When connecting machines in a swarm:

- Only connect trusted machines on trusted networks
- Use mutual TLS or other strong authentication between nodes
- Do not expose PNS ports to the public internet
- Network-segment swarms by trust level and function
- Monitor inter-node communication for unexpected patterns

The swarm can coordinate work across machines, which amplifies both capability and risk. Treat swarm networks as critical infrastructure.

### Audit and Monitoring

- Enable audit logging and regularly review logs for anomalies
- Monitor resource usage (CPU, memory, network) for unexpected spikes
- Set up alerts for failed tool executions or circuit breaker activations
- Periodically export and examine session state and memory artifacts

## Security Considerations by Use Case

### Healthcare & Life Sciences

**Strengths**: Are-Self's local-only architecture makes it HIPAA-aligned by design. PHI never touches cloud infrastructure.

**Operator responsibilities**:
- Ensure PostgreSQL runs on HIPAA-compliant infrastructure (encrypted storage, audited access)
- Restrict network access to the application to authorized users and systems only
- Implement user authentication and session management
- Maintain audit logs for compliance audits
- Use encryption in transit (TLS) for all API communication

### Research & Scientific Computing

**Strengths**: Local execution, transparent tool behavior, auditable decision-making.

**Operator responsibilities**:
- Monitor tool execution to detect data corruption or unexpected behavior
- Validate outputs against ground truth before acting on results
- Implement version control for tool definitions and prompts
- Track which models and LLM configurations produced which outputs (important for reproducibility)

### Automation & DevOps

**Strengths**: Circuit breakers, budget enforcement, and focus economy prevent runaway automation.

**Operator responsibilities**:
- Implement least-privilege access for all connected systems
- Use strong authentication (mutual TLS, API keys with scope limits)
- Monitor tool execution frequency and duration for signs of loops or cascades
- Test automation in staging before production deployment
- Have a kill switch or manual override mechanism readily available

### Web Scraping & Data Collection

**Caution**: Are-Self's autonomous execution makes it easy to unintentionally violate terms of service or laws governing automated access.

**Operator responsibilities**:
- Obtain explicit permission or ensure terms of service permit automated access
- Implement rate limiting within tool configuration to respect server resources
- Use appropriate User-Agent headers and follow robots.txt
- Do not bypass authentication or access controls
- Be aware of CFAA (Computer Fraud and Abuse Act) and equivalent laws in your jurisdiction

## Reporting Security Issues

If you discover a security vulnerability in Are-Self:

1. **Do not open a public GitHub issue**
2. **Do not discuss it in public channels**
3. **Contact the maintainers privately**: [security contact information to be added by project maintainers]
4. Include:
   - A clear description of the vulnerability
   - Steps to reproduce (if applicable)
   - Potential impact
   - Any suggested fixes (optional but helpful)

We will acknowledge receipt within 48 hours and work toward a fix and responsible disclosure timeline.

### What Constitutes a Security Issue

**Security issues include**:
- Arbitrary code execution or command injection
- Privilege escalation (unprivileged user gaining elevated access)
- Unauthorized access to memory, logs, or configuration
- Denial of service through framework design flaws
- Cryptographic weaknesses
- Bypass of intended constraints (Focus Economy, Hypothalamus budgets, etc.)
- Tool injection or parameter manipulation that bypasses validation

**Not security issues** (but valuable feedback):
- Missing features or capability limitations
- Performance issues or resource usage suggestions
- UI/UX improvements
- Documentation gaps
- Operational concerns that don't involve framework code flaws

## Compliance Posture Summary

### HIPAA

**Status**: Aligned by design.

Are-Self's local-only architecture means PHI never leaves your infrastructure unless you explicitly configure cloud failover and transmit data yourself. This eliminates the largest class of HIPAA violations (unauthorized transmission).

**Not included in framework**:
- User authentication and role-based access control (operator responsibility)
- Encryption key management (operator responsibility)
- Backup and disaster recovery procedures (operator responsibility)
- Audit log retention policies (operator responsibility)

### SOC 2 Type I

**Status**: Achievable with operator implementation.

The framework supports the technical controls required for SOC 2 Type I:
- Access logging via PostgreSQL audit features
- Encryption at rest via PostgreSQL encryption
- Isolated execution environment on consumer hardware
- No external dependencies or third-party log transmission

**Requires operator implementation**:
- Authentication and authorization policies
- Physical security (machine access control)
- Network security (firewall, segmentation)
- Backup and recovery procedures
- Formal change management

### GDPR

**Status**: No personal data collection by the framework itself.

Are-Self does not:
- Collect user behavioral data
- Transmit operational telemetry
- Build profiles of your usage
- Share data with third parties

**Note**: If you configure cloud failover or use tools that transmit data, those data flows are subject to GDPR in the EU. You become the data controller and are responsible for lawful processing, user consent, and data minimization.

### SOC 2 Type II, ISO 27001, etc.

These require ongoing compliance audits and formal control procedures. Are-Self provides the technical foundation, but achieving these certifications requires organizational processes outside the scope of framework code.

## Final Note on Risk

Are-Self is powerful. Power creates risk. This document exists because we respect that risk enough to name it.

The system includes multiple safeguards—the Focus Economy, the Parietal Lobe, the Hypothalamus, circuit breakers, and spike forensics. These are not perfect, and they are not a substitute for operator responsibility.

Running an autonomous reasoning system means:

- You choose what it can do (tool configuration)
- You choose what data it accesses (permissions and network access)
- You choose how it's deployed (cloud-exposed vs. air-gapped)
- You are responsible for what it does

This is not a black box. It is auditable, instrumentable, and controllable. Use that to your advantage. Understand the system you're deploying. Test it. Monitor it. Have a kill switch.

Are-Self was built for good. It can accomplish remarkable things. It can also go wrong if misused or deployed without care. We've given you the tools to deploy it safely. The rest is up to you.
