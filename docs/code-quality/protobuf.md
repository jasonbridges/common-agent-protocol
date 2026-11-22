# Protocol Buffers and API Schemas

Use this guide with the [code-quality index](README.md) and [readability principles](readability.md). Schema changes are changes to contracts: review callers, validators, generated bindings, and deployment compatibility.

## Repository authority

Read the component's interface specifications, accepted ADRs, and comments on affected messages before editing. Preserve standard wire types where specified rather than inventing a second transport or equivalent local message. A schema test proves properties of schemas; it does not prove a service is deployed, an implementation honors the schema, or two versions interoperate.

## Write for the caller and implementer

- Name messages and methods by their operation or domain concept. Make field units and meanings explicit; distinguish an identifier, digest, path, and label.
- Document each service, RPC, message, field, and enum value. Comments state presence rules, bounds, defaults, authority, failure behavior, and side effects.
- Keep messages focused on one operation or cohesive concept. Reuse shared types when their semantics match; avoid generic bags of options or an unrestricted `Any` when the accepted interface has a finite set of variants.
- Use standard timestamp/duration types and validate their allowed ranges. Explain which clock owns a deadline and whether an end is inclusive.
- Make absence meaningful: distinguish an omitted message, empty scalar, zero enum, and unset `oneof` according to the field's contract.
- Keep authentication and authorization inputs explicit. Verified identity comes from the authenticated transport/connection; a self-reported field cannot grant it.
- Define finite refusal classes/reasons. Callers must not parse prose error text to decide whether to retry, abort an action, or end a session.

## Evolve schemas without changing their meaning

[Protobuf field numbers](https://protobuf.dev/programming-guides/proto3/#assigning) identify the binary format. Never renumber or reuse them. If an approved breaking migration removes a field, reserve its number and name.

- Review names as well as numbers: JSON mappings expose field and enum names, so a binary-compatible rename can still break configuration or JSON consumers.
- Do not change type, cardinality, `oneof` membership, service method signature, or streaming kind without an explicit version/migration decision.
- Test supported revision pairs in both directions, rejected revisions, and rollback to the older binary.

## Strict validation considerations

Where a component's protocol or configuration reader rejects unknown fields, duplicate JSON keys, `null`, numeric-for-enum, or floating-point coercion, validate raw input **before** permissive decoding collapses distinct spellings. Preserve shared cross-language acceptance and rejection test vectors.

## Generation, build, and review checklist

Use the repository's checked-in build rules and dependency pins. Do not hand-edit generated bindings or run an arbitrary host `protoc` to repair a build.

Review malformed binary/JSON input, presence and size limits, refusal semantics, revision skew, descriptor compatibility, generated-source reproducibility, and consumer parity.

- [Protobuf Best Practices](https://protobuf.dev/best-practices/dos-donts/)
