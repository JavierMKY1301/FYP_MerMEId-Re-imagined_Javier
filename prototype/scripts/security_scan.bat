@echo off
REM ===================================================================
REM scripts\security_scan.bat - dependency, static and dynamic security
REM checks, mapped to the OWASP Top 10 (2021).
REM
REM The feedback noted that security testing was not mentioned at all.
REM This covers the three categories that apply to a read-only web
REM service over a public-domain dataset:
REM
REM   A03 Injection
REM       The API builds SPARQL by string interpolation. Covered by
REM       tests\test_api_contract.py::TestInjection and by the ZAP
REM       active scan below.
REM   A06 Vulnerable and outdated components
REM       pip-audit and npm audit, below.
REM   A05 Security misconfiguration
REM       ZAP's passive scan reports missing security headers, verbose
REM       errors and permissive CORS.
REM
REM Prerequisite: the API running on port 8000 and the portal on 5173.
REM
REM Usage:  cd prototype  &&  scripts\security_scan.bat
REM Results are written to results\security\.
REM ===================================================================

setlocal
set OUT=results\security
if not exist %OUT% mkdir %OUT%

echo.
echo === 1. Python dependency audit (OWASP A06) ===
py -m pip install --quiet pip-audit
py -m pip_audit --format columns > %OUT%\pip_audit.txt 2>&1
type %OUT%\pip_audit.txt

echo.
echo === 2. JavaScript dependency audit (OWASP A06) ===
pushd ..\portal
call npm audit --audit-level=moderate > ..\prototype\%OUT%\npm_audit.txt 2>&1
type ..\prototype\%OUT%\npm_audit.txt
popd

echo.
echo === 3. Injection tests against the live API (OWASP A03) ===
py -m pytest tests\test_api_contract.py -k "Injection" -v > %OUT%\injection_tests.txt 2>&1
type %OUT%\injection_tests.txt

echo.
echo === 4. OWASP ZAP baseline scan, API (A05, passive) ===
REM Runs ZAP in Docker so nothing needs installing. host.docker.internal
REM is how a container reaches a server on the Windows host.
docker run --rm -v "%cd%\%OUT%:/zap/wrk/:rw" ^
  ghcr.io/zaproxy/zaproxy:stable zap-baseline.py ^
  -t http://host.docker.internal:8000/docs ^
  -r zap_api_report.html -J zap_api_report.json -I
echo ZAP API report written to %OUT%\zap_api_report.html

echo.
echo === 5. OWASP ZAP baseline scan, portal ===
docker run --rm -v "%cd%\%OUT%:/zap/wrk/:rw" ^
  ghcr.io/zaproxy/zaproxy:stable zap-baseline.py ^
  -t http://host.docker.internal:5173 ^
  -r zap_portal_report.html -J zap_portal_report.json -I
echo ZAP portal report written to %OUT%\zap_portal_report.html

echo.
echo === Done ===
echo Record in the evaluation chapter:
echo   - vulnerable dependencies by severity, before and after any upgrade
echo   - injection test results (expect all passing)
echo   - ZAP alerts by risk level, and which were accepted rather than fixed
echo.
echo Note: ZAP will flag missing security headers such as Content-Security-Policy
echo on the development server. Decide per alert whether to fix it or to record
echo it as accepted for a local research prototype
endlocal
