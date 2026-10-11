#!/usr/bin/env python3
"""
Check for hardcoded credentials and sensitive values in the codebase.
This script helps identify potential security issues.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Patterns to search for
PATTERNS = {
    "passwords": [
        (r'password\s*=\s*["\'](...!.*{|.*\$|.*env)[^"\']{3,}["\']', "Hardcoded password"),
        (r'pwd\s*=\s*["\'][^"\']+["\']', "Hardcoded password (pwd)"),
    ],
    "api_keys": [
        (r'api[_-]...key\s*=\s*["\'](...!.*{|.*\$|.*env)[a-zA-Z0-9_-]{20,}["\']', "Hardcoded API key"),
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key"),
        (r'AKIA[0-9A-Z]{16}', "AWS Access Key"),
    ],
    "tokens": [
        (r'token\s*=\s*["\'](...!mock_token|.*{|.*\$|.*env)[^"\']{10,}["\']', "Hardcoded token"),
        (r'bearer\s+[a-zA-Z0-9_-]{20,}', "Bearer token"),
    ],
    "urls": [
        (r'https...://(...!localhost|127\.0\.0\.1)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(...:/[^\s"\'\)]*)...', "External URL (check if sensitive)"),
    ],
    "emails": [
        (r'[a-zA-Z0-9._%+-]+@(...!redteam\.local|example\.com|yourdomain\.com)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', "Real email address"),
    ],
    "secrets": [
        (r'secret[_-]...key\s*=\s*["\'](...!.*{|.*\$|.*env)[^"\']{10,}["\']', "Hardcoded secret key"),
        (r'private[_-]...key\s*=\s*["\'][^"\']+["\']', "Hardcoded private key"),
    ],
}

# Files and directories to skip
SKIP_PATTERNS = [
    r'\.git/',
    r'node_modules/',
    r'\.venv/',
    r'__pycache__/',
    r'\.pytest_cache/',
    r'\.ruff_cache/',
    r'\.next/',
    r'dist/',
    r'build/',
    r'\.egg-info/',
    r'\.pyc$',
    r'\.pyo$',
    r'\.so$',
    r'\.dll$',
    r'\.dylib$',
    r'package-lock\.json$',
    r'pnpm-lock\.yaml$',
    r'yarn\.lock$',
    # Documentation files are allowed to have examples
    r'\.md$',
    r'\.rst$',
    r'\.txt$',
    # This script itself
    r'check_hardcoded_values\.py$',
]

def should_skip(file_path: str) -> bool:
    """Check if file should be skipped."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False

def check_file(file_path: Path) -> List[Tuple[str, int, str, str]]:
    """
    Check a single file for hardcoded values.
    Returns list of (category, line_number, line_content, description)
    """
    findings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        for line_num, line in enumerate(lines, 1):
            # Skip comments (basic check)
            if line.strip().startswith('#') or line.strip().startswith('//'):
                continue
                
            for category, patterns in PATTERNS.items():
                for pattern, description in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append((
                            category,
                            line_num,
                            line.strip(),
                            description
                        ))
                        
    except Exception as e:
        print(f"[WARN]️  Error reading {file_path}: {e}")
        
    return findings

def scan_directory(root_path: Path) -> dict:
    """Scan directory recursively for hardcoded values."""
    all_findings = {}
    
    for file_path in root_path.rglob('*'):
        if not file_path.is_file():
            continue
            
        relative_path = str(file_path.relative_to(root_path))
        
        if should_skip(relative_path):
            continue
            
        # Only check certain file types
        if not any(file_path.suffix in ext for ext in ['.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml', '.env', '.sh']):
            continue
            
        findings = check_file(file_path)
        if findings:
            all_findings[relative_path] = findings
            
    return all_findings

def print_findings(findings: dict):
    """Print findings in a readable format."""
    if not findings:
        print("\n[OK] No hardcoded sensitive values found!")
        print("   All credentials appear to be externalized to environment variables.")
        return
        
    print(f"\n[WARN]️  Found {len(findings)} files with potential hardcoded values:\n")
    
    for file_path, file_findings in sorted(findings.items()):
        print(f"[FILE] {file_path}")
        
        for category, line_num, line_content, description in file_findings:
            print(f"   Line {line_num} [{category}]: {description}")
            print(f"   > {line_content[:100]}")
            print()

def print_summary(findings: dict):
    """Print summary statistics."""
    if not findings:
        return
        
    total_issues = sum(len(f) for f in findings.values())
    categories = {}
    
    for file_findings in findings.values():
        for category, _, _, _ in file_findings:
            categories[category] = categories.get(category, 0) + 1
            
    print("=" * 70)
    print(f"Summary: {total_issues} potential issues found in {len(findings)} files")
    print("=" * 70)
    
    for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")
        
    print("\n[WARN]️  Note: Some findings may be false positives.")
    print("   Review each finding to determine if it's a real security issue.")
    print("\n[TIP] Recommendation:")
    print("   - Move all credentials to environment variables")
    print("   - Use .env files for local development")
    print("   - Never commit .env files to version control")
    print("   - Use secret management systems in production")

def main():
    """Main execution."""
    print("=" * 70)
    print("ARTEF Hardcoded Values Security Scanner")
    print("=" * 70)
    
    # Scan from project root
    root_path = Path(__file__).parent.parent
    print(f"\n[INFO] Scanning directory: {root_path}")
    print("   (This may take a moment...)\n")
    
    findings = scan_directory(root_path)
    
    print_findings(findings)
    print_summary(findings)
    
    # Return exit code
    return 1 if findings else 0

if __name__ == "__main__":
    exit(main())
