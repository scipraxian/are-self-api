# Adjust this path to wherever you extracted the zip
$src = "."
$dst = "C:\Users\micha\are-self\are-self-api\nginx\certs"

# Nginx wants server cert + intermediate chain in one file, server cert first
Get-Content "$src\certificate.crt","$src\ca_bundle.crt" | Set-Content "$dst\cert.pem" -Encoding ascii
Copy-Item "$src\private.key" "$dst\key.pem" -Force

# Sanity check
Get-ChildItem $dst