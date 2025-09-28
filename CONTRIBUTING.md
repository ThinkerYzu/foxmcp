# Contributing to FoxMCP

Thank you for your interest in contributing to FoxMCP! This document provides guidelines for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by our code of conduct:
- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect different viewpoints and experiences

## How to Contribute

### Reporting Issues

1. **Search existing issues** first to avoid duplicates
2. **Use clear, descriptive titles** for your issues
3. **Provide detailed information** including:
   - Steps to reproduce the issue
   - Expected vs actual behavior
   - Your environment (OS, Firefox version, Python version)
   - Relevant logs or error messages

### Submitting Changes

1. **Fork the repository** on GitHub
2. **Create a feature branch** from `master`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following our coding standards
4. **Add tests** for new functionality
5. **Run the test suite** to ensure everything passes:
   ```bash
   make test
   ```
6. **Commit your changes** with clear, descriptive messages
7. **Push to your fork** and submit a pull request

### Pull Request Guidelines

- **Keep PRs focused** - one feature or fix per PR
- **Write clear descriptions** explaining what your PR does
- **Include tests** for new features or bug fixes
- **Update documentation** as needed
- **Follow the existing code style**
- **Ensure all tests pass** before submitting

## Development Setup

See [docs/development.md](docs/development.md) for detailed development setup instructions.

### Quick Start

```bash
# Clone your fork
git clone https://github.com/your-username/foxmcp.git
cd foxmcp

# Setup development environment
make dev

# Run tests
make test

# Build extension
make build
```

## Coding Standards

### Python Code

- Follow **PEP 8** style guidelines
- Use **type hints** for function parameters and return values
- Write **docstrings** for all public functions and classes
- Use **meaningful variable names**
- Keep functions **small and focused**

```python
def process_browser_request(message: dict) -> dict:
    """Process incoming browser request message.

    Args:
        message: WebSocket message from browser extension

    Returns:
        Processed response dictionary
    """
    # Implementation here
    pass
```

### JavaScript Code

- Use **modern JavaScript** (ES6+)
- Follow **consistent indentation** (2 spaces)
- Use **meaningful variable names**
- Add **comments** for complex logic
- Use **async/await** for asynchronous operations

```javascript
/**
 * Send message to background script
 * @param {Object} message - Message to send
 * @returns {Promise<Object>} Response from background script
 */
async function sendMessage(message) {
  return browser.runtime.sendMessage(message);
}
```

### Testing

- **Write tests** for all new features
- **Maintain test coverage** above 80%
- **Use descriptive test names** that explain what is being tested
- **Test both success and error cases**

```python
@pytest.mark.asyncio
async def test_tab_creation_with_valid_url(self, server_with_extension):
    """Test that valid URLs create tabs successfully"""
    # Test implementation
    pass
```

## Documentation

- **Update documentation** when adding new features
- **Use clear, concise language**
- **Include code examples** where helpful
- **Keep documentation up to date** with code changes

## Commit Messages

Use clear, descriptive commit messages:

```
Add tab screenshot functionality

- Implement tabs_capture_screenshot tool
- Support PNG and JPEG formats
- Add quality parameter for JPEG
- Include comprehensive tests
```

Format:
- **First line**: Brief summary (50 characters or less)
- **Blank line**
- **Body**: Detailed explanation if needed
- **Use bullet points** for multiple changes

## Release Process

Releases are handled by maintainers, but contributors should:
- **Update version numbers** in relevant files when making breaking changes
- **Update CHANGELOG.md** with notable changes
- **Ensure all tests pass** on supported platforms

## Getting Help

- **Read the documentation** in the `docs/` directory
- **Check existing issues** for similar problems
- **Ask questions** by opening a new issue with the "question" label
- **Join discussions** in existing issues and pull requests

## Recognition

Contributors are recognized in several ways:
- **Listed in release notes** for significant contributions
- **Mentioned in commit messages** when appropriate
- **Added to contributor lists** in documentation

## Types of Contributions

We welcome many types of contributions:

### Code Contributions
- **Bug fixes**
- **New browser functions**
- **Performance improvements**
- **Security enhancements**

### Documentation
- **API documentation**
- **Tutorial improvements**
- **Example scripts**
- **Translation** (future consideration)

### Testing
- **Additional test cases**
- **Integration tests**
- **Performance tests**
- **Security tests**

### Community
- **Helping other users**
- **Reviewing pull requests**
- **Reporting bugs**
- **Feature suggestions**

## License

By contributing to FoxMCP, you agree that your contributions will be licensed under the same MIT License that covers the project. See [LICENSE](LICENSE) file for details.

## Questions?

If you have questions about contributing, please:
1. Check this document first
2. Look at existing issues and discussions
3. Open a new issue with the "question" label

Thank you for contributing to FoxMCP!