[CmdletBinding()]
param(
    [string]$CrioHost = '192.168.1.2',
    [ValidateRange(1, 65535)]
    [int]$CrioPort = 9070,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [ValidateRange(100, 60000)]
    [int]$ConnectTimeoutMs = 3000,
    [ValidateRange(100, 60000)]
    [int]$FirstByteTimeoutMs = 25000,
    [ValidateRange(25, 5000)]
    [int]$IdleTimeoutMs = 250,
    [ValidateRange(1, 1048576)]
    [int]$MaxResponseBytes = 8192
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# The supplied Socket Test VI contains the literal three-byte request GET. Keep
# this fixed: the probe is an input-only evidence capture, not a general command
# client. In particular, do not append CR, LF, or NUL without wire evidence.
$Request = [Text.Encoding]::ASCII.GetBytes('GET')
$Client = $null
$Stream = $null
$Buffer = [byte[]]::new([Math]::Min(1024, $MaxResponseBytes))
$Response = [IO.MemoryStream]::new()

function Test-ReadTimeout {
    param([Parameter(Mandatory = $true)][Management.Automation.ErrorRecord]$Record)
    $Exception = $Record.Exception
    while ($null -ne $Exception) {
        if ($Exception -is [Net.Sockets.SocketException] -and
            $Exception.SocketErrorCode -eq [Net.Sockets.SocketError]::TimedOut) {
            return $true
        }
        $Exception = $Exception.InnerException
    }
    return $false
}

try {
    if (Test-Path -LiteralPath $OutputPath) {
        throw "output already exists; refusing to overwrite evidence: $OutputPath"
    }

    $Client = [Net.Sockets.TcpClient]::new()
    $Connect = $Client.ConnectAsync($CrioHost, $CrioPort)
    if (-not $Connect.Wait($ConnectTimeoutMs)) {
        throw "cRIO TCP connect timed out after $ConnectTimeoutMs ms"
    }
    # Observe exceptions from a completed faulted ConnectAsync task.
    $null = $Connect.GetAwaiter().GetResult()

    $Stream = $Client.GetStream()
    $Stream.WriteTimeout = $ConnectTimeoutMs
    $Stream.ReadTimeout = $FirstByteTimeoutMs
    $Stream.Write($Request, 0, $Request.Length)
    $Stream.Flush()

    $ReceivedAny = $false
    while ($true) {
        try {
            $Read = $Stream.Read($Buffer, 0, $Buffer.Length)
        }
        catch {
            if ($ReceivedAny -and (Test-ReadTimeout -Record $_)) { break }
            if (-not $ReceivedAny -and (Test-ReadTimeout -Record $_)) {
                throw "cRIO returned no response within $FirstByteTimeoutMs ms after GET"
            }
            throw
        }
        if ($Read -eq 0) { break }
        if (($Response.Length + $Read) -gt $MaxResponseBytes) {
            throw "cRIO response exceeds $MaxResponseBytes bytes; refusing a partial capture"
        }
        $Response.Write($Buffer, 0, $Read)
        $ReceivedAny = $true
        $Stream.ReadTimeout = $IdleTimeoutMs
    }

    if (-not $ReceivedAny) {
        throw 'cRIO closed the connection without a response'
    }

    $Bytes = $Response.ToArray()
    $File = [IO.File]::Open($OutputPath, [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $File.Write($Bytes, 0, $Bytes.Length); $File.Flush() }
    finally { $File.Dispose() }

    $Sha256 = [Security.Cryptography.SHA256]::Create()
    try { $Hash = ([BitConverter]::ToString($Sha256.ComputeHash($Bytes))).Replace('-', '') }
    finally { $Sha256.Dispose() }

    [pscustomobject]@{
        endpoint     = "${CrioHost}:$CrioPort"
        request_hex  = ([BitConverter]::ToString($Request)).Replace('-', '')
        bytes        = $Bytes.Length
        sha256       = $Hash
        output_path  = [IO.Path]::GetFullPath($OutputPath)
    } | ConvertTo-Json -Compress
}
finally {
    $Response.Dispose()
    if ($null -ne $Stream) { $Stream.Dispose() }
    if ($null -ne $Client) { $Client.Dispose() }
}
