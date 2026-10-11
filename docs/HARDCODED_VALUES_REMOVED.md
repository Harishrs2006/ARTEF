# Hardcoded Values Removal - Security Enhancement

## Overview

This document details the removal of hardcoded values from the ARTEF (Agent Red-Teaming & Evaluation Framework) project to improve security and configurability.

## Changes Made

### 1. User Credentials (scripts/seed_demo_data.py)

**Before:**
- Passwords were hardcoded directly in the seed script
- Email addresses used fixed domain

**After:**
- All passwords now configurable via environment variables
- Email domain configurable via `SEED_EMAIL_DOMAIN`

**Environment Variables Added:**
```bash
SEED_ADMIN_PASSWORD=admin123
SEED_SAFETY_PASSWORD=safety123
SEED_ML_PASSWORD=ml123
SEED_QA_PASSWORD=qa123
SEED_REVIEWER_PASSWORD=reviewer123
SEED_VIEWER_PASSWORD=viewer123
SEED_EMAIL_DOMAIN=redteam.local
```

### 2. Agent Endpoints (scripts/seed_demo_data.py)

**Before:**
- Agent URLs were hardcoded (localhost:8001, localhost:8002, etc.)
- Authentication tokens were hardcoded as "mock_token"

**After:**
- All agent endpoints configurable via environment variables
- Authentication tokens configurable

**Environment Variables Added:**
```bash
SEED_PROD_AGENT_URL=http://localhost:8001/agent/chat
SEED_STAGING_AGENT_URL=http://localhost:8002/agent/chat
SEED_MOCK_AGENT_V1_URL=http://localhost:9001/chat
SEED_MOCK_AGENT_V2_URL=http://localhost:9002/chat
SEED_AGENT_AUTH_TOKEN=mock_token
```

### 3. Admin User Creation (scripts/create_admin_user.py)

**Before:**
- Database URL was hardcoded
- Admin credentials were hardcoded

**After:**
- Database URL from `DATABASE_URL` environment variable
- All admin credentials configurable

**Environment Variables Added:**
```bash
ADMIN_EMAIL=admin@redteam.local
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_FULLNAME=Admin User
```

### 4. Production Environment Template (scripts/fix_critical_issues.py)

**Before:**
- Template contained example API key "sk-..."

**After:**
- Clear placeholder text for sensitive values
- Added admin user configuration section

## Security Benefits

1. **No Credential Exposure**: Credentials no longer stored in source code
2. **Environment-Specific Configuration**: Different values for dev/staging/prod
3. **Easy Rotation**: Change credentials without code changes
4. **Version Control Safe**: Sensitive values not committed to git
5. **Docker-Friendly**: Environment variables work seamlessly with containers

## Migration Guide

### For Development

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update values as needed (defaults work for local development)

3. Run seed scripts:
   ```bash
   cd backend
   python ../scripts/seed_demo_data.py
   ```

### For Production

1. **Never use default credentials in production!**

2. Set strong passwords via environment variables:
   ```bash
   export ADMIN_PASSWORD="$(openssl rand -base64 32)"
   export SEED_ADMIN_PASSWORD="$ADMIN_PASSWORD"
   ```

3. Use proper agent endpoints:
   ```bash
   export SEED_PROD_AGENT_URL="https://api.yourdomain.com/agent/chat"
   export SEED_AGENT_AUTH_TOKEN="$(openssl rand -hex 32)"
   ```

4. Set custom email domain:
   ```bash
   export SEED_EMAIL_DOMAIN="yourdomain.com"
   ```

## Configuration Reference

### Quick Setup (Development)

```bash
# Copy example file
cp .env.example .env

# Edit as needed (defaults work for dev)
nano .env

# Seed the database
npm run seed
```

### Production Checklist

- [ ] Change all default passwords
- [ ] Set production database URL
- [ ] Configure real agent endpoints
- [ ] Generate secure authentication tokens
- [ ] Set production email domain
- [ ] Review all environment variables
- [ ] Test configuration before deployment

## Fallback Behavior

All configuration has safe fallback defaults for development:

- **Passwords**: Default development passwords (change in production!)
- **URLs**: localhost with standard ports
- **Email**: redteam.local domain
- **Tokens**: "mock_token" (for testing only)

⚠️ **WARNING**: Default values are **INSECURE** and only suitable for local development. Always configure secure values for staging and production environments.

## Files Modified

1. `scripts/seed_demo_data.py` - User and agent seeding
2. `scripts/create_admin_user.py` - Admin user creation
3. `scripts/fix_critical_issues.py` - Production template
4. `.env.example` - Documentation and defaults

## Testing

Verify the changes work correctly:

```bash
# Test with default values
npm run seed

# Test with custom values
export SEED_ADMIN_PASSWORD="custom_password"
export SEED_EMAIL_DOMAIN="example.com"
npm run seed

# Verify users were created with correct values
# (Check database or login to application)
```

## Additional Notes

- The frontend already uses `NEXT_PUBLIC_API_URL` for configuration
- Backend database connection uses `DATABASE_URL`
- JWT keys should use `JWT_PRIVATE_KEY_PATH` and `JWT_PUBLIC_KEY_PATH`
- All LLM provider API keys are already configurable

## Support

For questions or issues related to configuration:
1. Check `.env.example` for all available variables
2. Review individual script documentation
3. Consult the main README.md for deployment guides

---

**Last Updated**: January 2026  
**Author**: Security Enhancement Initiative
