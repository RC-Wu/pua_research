# Contributing to CatfishResearch

[English](CONTRIBUTING.md) | [中文版](CONTRIBUTING_CN.md)

Thank you for your interest in contributing to CatfishResearch. This repository preserves the upstream ARIS workflow lineage and the Codex-first fork history, so contributions should keep provenance explicit when updating top-level docs, `docs/catfish/`, or fork-specific execution notes.

## Ways to Contribute

- Report bugs or issues
- Suggest new features or skills
- Improve documentation
- Add translations
- Share your use cases and feedback

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_FORK.git
   cd YOUR_FORK
   ```
3. Create a branch for your changes:
   ```bash
   git checkout -b your-feature-name
   ```

## Development

### Skill Development

Skills are Markdown files located in `skills/`. Each skill has:

- **Frontmatter**: YAML metadata (name, description, allowed-tools)
- **Content**: The skill instructions

Example skill structure:
```markdown
---
name: my-skill
description: What this skill does
argument-hint: [optional-argument-hint]
allowed-tools: Read, Write, Bash(*)
---

# Skill Title

Instructions here...
```

### Testing Your Changes

Before submitting:
1. Install your modified skill: `cp -r skills/your-skill ~/.claude/skills/`
2. Test in Claude Code: `/your-skill test argument`
3. Verify the skill works as expected

## Pull Request Process

1. Make sure your changes are well-documented
2. Update `README.md` or `docs/catfish/` if you add Catfish-facing docs, naming, or feature surfaces
3. Keep PRs focused on a single change
4. Write clear commit messages

### PR Checklist

- [ ] Code follows the project style
- [ ] Documentation is updated (if applicable)
- [ ] Changes are tested locally

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Questions?

Feel free to open an issue for any questions or join our WeChat group (QR code in README).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
