# Optional GNU Make forwarding layer. All behavior lives in dar.ps1.
POWERSHELL ?= pwsh
TARGETS := help up up-lite down reset seed health verify simulate-day backup restore licenses lint-branding lint-code lint venv generate-secrets rotate-s3-identity test-env-file tofu-init tofu-plan tofu-apply s3-conformance smoke-m1 verify-opensearch verify-opa traceability smoke-m2 smoke-m3 benchmark demo clean
.PHONY: $(TARGETS)
$(TARGETS):
	$(POWERSHELL) -NoProfile -ExecutionPolicy Bypass -File ./dar.ps1 $@
