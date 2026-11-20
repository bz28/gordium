# One time, per Windows user, on the trial machine: makes a code-signing certificate that exists only on this machine
# and trusts it for this user, so Revit loads the Gordium add-in signed with it without asking "Always Load" after
# every build (Revit trusts a signed add-in's publisher; an unsigned one is asked about again whenever its file changes).
# install_trial_addin.ps1 then signs every build with it. Windows asks once to trust the certificate (click Yes).
# Undo: remove "Gordium trial add-in (this machine)" from certmgr.msc: Personal, Trusted Publishers and Trusted Root.
$ErrorActionPreference = "Stop"
$subject = "CN=Gordium trial add-in (this machine)"
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq $subject -and $_.NotAfter -gt (Get-Date) } |
    Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $cert) {
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $subject -CertStoreLocation Cert:\CurrentUser\My `
        -NotAfter (Get-Date).AddYears(3) -KeyExportPolicy NonExportable -HashAlgorithm SHA256
    "Made the certificate $($cert.Thumbprint)"
}
$public = Join-Path $env:TEMP "gordium_trial_addin.cer"
Export-Certificate -Cert $cert -FilePath $public | Out-Null
foreach ($store in "TrustedPublisher", "Root") {
    if (-not (Get-ChildItem "Cert:\CurrentUser\$store" | Where-Object Thumbprint -eq $cert.Thumbprint)) {
        Import-Certificate -FilePath $public -CertStoreLocation "Cert:\CurrentUser\$store" | Out-Null   # Root: Windows asks once
        "Trusted for this user: $store"
    }
}
Remove-Item $public
"Ready: $subject ($($cert.Thumbprint)), valid until $($cert.NotAfter.ToString('yyyy-MM-dd'))"
