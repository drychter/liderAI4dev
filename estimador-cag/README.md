#####
Request example body

{
  "transcription": "The client want to build a real estate cloud pageservice, to manage its portfolio, and client registration. Every 2 weekends a marketing email is sent to client highlighting the portfolio"
}

#####
LLM respose body
{
  "estimation": "# Estimation: Real Estate Cloud Platform\n\n### Task breakdown:\n1. UI/UX design (portal + admin): 50 hours\n2. Client registration and authentication: 25 hours\n3. Property portfolio management (CRUD, uploads, filtering): 70 hours\n4. Admin panel for property management: 40 hours\n5. Email marketing automation (bi-weekly campaigns): 20 hours\n6. Database design and optimization: 25 hours\n7. API development and integrations: 35 hours\n8. Testing and QA: 35 hours\n9. Deployment, security, and infrastructure setup: 20 hours\n\n**Total estimated: 320 hours**\n**Recommended team: 2 full-stack developers, 1 backend developer, 1 UX designer (part-time)**\n**Estimated duration: 10-12 weeks**\n\n### Key considerations:\n- Property image/document storage (cloud storage integration)\n- Email template builder for marketing campaigns\n- Scalable database for large property portfolios\n- Analytics dashboard for campaign performance\n- Optional: Integration with MLS/property listing services for future expansion",
  "model": "claude-haiku-4-5-20251001",
  "provider": "anthropic",
  "total_tokens": 1012
}