# Upstream attribution and dependency scope

The example executes `@joshuacalpuerto/mcp-agent` version **1.1.1**, authored by Joshua C Alpuerto. Its package metadata declares the **MIT** license. We import the npm distribution and do not vendor or alter the upstream implementation. The adapter, fixtures, and checker in this directory are RunLedger example code under this repository's MIT license.

- [Upstream repository](https://github.com/joshuaalpuerto/mcp-agent)
- [Published source revision](https://github.com/joshuaalpuerto/mcp-agent/tree/28946564ef1bcd001b8e49f3f62ba3a4c2dec258): `28946564ef1bcd001b8e49f3f62ba3a4c2dec258` (npm `gitHead` for 1.1.1)
- [Actual Agent implementation](https://github.com/joshuaalpuerto/mcp-agent/blob/28946564ef1bcd001b8e49f3f62ba3a4c2dec258/src/agent/index.ts)
- [Original merged RunLedger integration, PR #3](https://github.com/joshuaalpuerto/mcp-agent/pull/3): the maintainer confirmed the `Agent.callTool` boundary. This example uses registered function callbacks, preserving the upstream method itself.
- npm tarball integrity: `sha512-4Yx7QyjgMgy30iBqDiK1dAYXZj6NQJCXJnlhiFJvOZLvJMadufJaklnYy+mNCZpVNvw+dlJRpVU8GmspGfqBvw==`

The upstream package requires Node >=21. We test on Node 22. Its emitted JavaScript contains extensionless ESM imports, so the example pins `tsx` 4.23.15 to resolve them. `package-lock.json` pins transitive dependencies and integrity hashes; use `npm ci --ignore-scripts`, not an unreviewed upgrade or `npm audit fix --force`.

## Known advisories in this frozen example

On **2026-10-27**, `npm audit` for the committed lockfile reported five vulnerable package entries: four high and one moderate. The four high entries include packages affected transitively; they are not four independent high-severity flaws. The underlying advisories were:

| Affected dependency | Severity | Advisory and affected range |
| --- | --- | --- |
| `langsmith` 0.3.14 | High | [Public prompt deserialization](https://github.com/advisories/GHSA-3644-q5cj-c5c7), npm `<0.6.0` |
| `zod` 3.24.2 | High | [Excessive memory use validating collections](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5), `<4.6.6` |
| `langsmith` 0.3.14 | Moderate | [Prototype pollution](https://github.com/advisories/GHSA-fw9q-39r9-c252), `<=0.5.17` |
| `langsmith` 0.3.14 | Moderate | [Streaming output redaction bypass](https://github.com/advisories/GHSA-rr7j-v2q5-chgv), `<=0.5.18` |
| `uuid` 10.0.0, transitively | Moderate | [Missing buffer bounds checks](https://github.com/advisories/GHSA-w5hq-g745-h8pq), `<11.1.1` |

These dependencies are installed only in this optional example. They are not added to RunLedger's Python package or its root development dependencies. The acceptance checker forwards no API credentials, uses only the small committed fixtures, and verifies that the adapter rejects Node fetch/socket/TLS connection attempts. It does not invoke LangSmith prompt loading, streaming tracing, or a real provider. This limits the demonstrated test surface; it does not repair the dependencies or make this a security sandbox.

Use a maintained, reviewed dependency set before adapting this pattern to live services or untrusted input. We preserve the historical package pin to make the compatibility test reproducible instead of overriding upstream to incompatible major versions. Recheck current advisories with:

```bash
npm --prefix examples/mcp-agent audit
```
