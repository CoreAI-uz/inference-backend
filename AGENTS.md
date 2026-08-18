# Repository instructions

These instructions apply to the entire repository.

## Public website copy

User-facing copy must read as finished product communication. It must not reveal or imply the
internal discussion, design debate, prompting, rejected alternatives, or reasoning that led to a
decision.

### Hard rule: no defensive or meta copy

Do not publish copy that:

- answers an objection the visitor did not raise;
- explains why CoreAI chose one positioning, architecture, protocol, SDK, or design over another;
- distances CoreAI from a vendor, tool, category, or prior implementation;
- turns an internal instruction or the user's rationale into marketing or documentation text;
- tells visitors what the product "really is," "is first," "does not define," or is "not required"
  when the interface can simply state the relevant fact;
- justifies the order or presence of examples, sections, controls, or features;
- uses phrases such as "for migration convenience," "we chose this because," "unlike other
  providers," "this is not...," or "rather than..." as positioning commentary.

Bad:

> CoreAI is an HTTP API first. Compatible clients are supported for migration convenience, but
> they do not define the product.

Good:

> Base URL: `https://inference-api.coreai.uz/v1`

Bad:

> cURL is shown first because it documents the actual HTTP contract.

Good:

> Send your first request.

### Write only what the visitor needs

Prefer:

- concrete capabilities and benefits;
- direct instructions;
- accurate endpoint, parameter, pricing, availability, and compatibility facts;
- short labels and examples that stand on their own;
- confident copy with no explanation of the internal decision behind it.

Necessary negative statements are allowed when they directly communicate a material fact, such as
privacy commitments, security warnings, legal terms, current feature availability, API errors, or
unsupported parameters. State these plainly and briefly; do not attach internal rationale.

### Review requirement

Before completing any website-copy change, review the rendered copy as a visitor would and ask:

1. Does any sentence sound like it came from an internal debate or prompt?
2. Does any sentence defend a decision instead of communicating a fact?
3. Does any sentence mention an alternative that the visitor did not need to hear about?
4. Can the sentence be replaced by a label, fact, example, or direct instruction?

If any answer is yes, rewrite or remove the sentence. Do not transfer the user's private reasoning
into public copy unless the user explicitly asks for that exact reasoning to appear publicly.
