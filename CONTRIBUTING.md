# Contributing to R4GV1S

Thank you for helping improve the knowledge base! Contributions are what make R4GV1S more useful for the community.

## What You Can Contribute

- **CVE entries** — exploits and detection commands for specific CVEs
- **Methodologies** — step-by-step attack techniques (web, network, privesc, etc.)
- **Tool notes** — usage guides, flags, and tips for pentest tools
- **Bug fixes** — improvements to the codebase

## Knowledge Base Contributions

### CVE Entry

Use the template at `knowledge-base/_templates/cve-template.yaml`.

Place your file at:
```
knowledge-base/cves/YEAR/CVE-YYYY-XXXXX.yaml
```

**Required fields:** `id`, `title`, `affected`, `severity`, `tags`, `commands`

**Example:**
```yaml
id: CVE-2024-1234
title: Apache mod_rewrite RCE via crafted URL
affected: Apache HTTP Server 2.4.0 - 2.4.59
severity: critical
tags: [rce, apache, webserver]
commands:
  - description: Check if target is vulnerable
    cmd: curl -s "http://{target}/cgi-bin/.../%2e%2e/%2e%2e/bin/sh" -d "echo;id"
references:
  - https://nvd.nist.gov/vuln/detail/CVE-2024-1234
```

### Methodology

Use the template at `knowledge-base/_templates/methodology-template.md`.

Place your file at:
```
knowledge-base/methodologies/CATEGORY/your-topic.md
```

Categories: `web`, `network`, `privesc`, `mobile`, `cloud`, `hardware`

### Tool Notes

Place at:
```
knowledge-base/tools/toolname.md
```

## Pull Request Process

1. Fork the repository
2. Create a branch: `git checkout -b kb/cve-2024-1234` or `kb/sqli-methodology`
3. Add your file(s)
4. Make sure YAML files are valid: `python -c "import yaml; yaml.safe_load(open('your-file.yaml'))"`
5. Submit a PR with a clear title and description

## Code Contributions

For code changes, please:
- Keep PRs focused on a single change
- Test your changes locally
- Update documentation if needed

## Quality Guidelines

- Commands must use `{placeholder}` syntax for variable parts
- Include at least one reference link for CVE entries
- Keep methodology steps clear and numbered
- Test commands before submitting when possible

## Placeholder Convention

Use these standard placeholders in commands:

| Placeholder | Meaning |
|---|---|
| `{target}` | Target hostname or IP |
| `{ip}` | IP address |
| `{port}` | Port number |
| `{url}` | Full URL |
| `{lhost}` | Attacker's IP |
| `{lport}` | Listener port |
| `{user}` | Username |
| `{pass}` | Password |
