[CmdletBinding()]
param(
    [ValidateSet('Psp', 'Fixture')]
    [string]$Source = 'Fixture',
    [ValidateSet('File', 'Tcp')]
    [string]$Sink = 'File',
    [string]$FixturePath,
    [string]$OutputPath,
    [string]$CrioHost = '192.168.1.2',
    [string]$GatewayHost = '192.168.1.1',
    [int]$GatewayPort = 9070,
    [ValidateRange(1, 60000)]
    [int]$CadenceMs = 3000,
    [ValidateRange(100, 60000)]
    [int]$ReconnectDelayMs = 5000,
    [ValidateRange(0, 5000)]
    [int]$ConnectSpacingMs = 100,
    [ValidateRange(1, 60000)]
    [int]$FreshnessMs = 5000,
    [ValidateRange(0, 60000)]
    [int]$MaxSkewMs = 2000,
    [ValidateRange(128, 1048576)]
    [int]$MaxLineBytes = 8192,
    [ValidateRange(0, 2147483647)]
    [int]$MaxFrames = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Fixture-only contract fields. Fixture mode exercises the downstream contract;
# it never opens NI-PSP or a cRIO resource.
$FixtureAllowlist = @(
    'PL_top_condenser_temp', 'PL_bottom_condenser_temp',
    'MT_top', 'MT_bottom',
    'PL_bottom1', 'PL_bottom2', 'PL_bottom3', 'PL_bottom4',
    'PL_chamber_pressure', 'PL_output_pressure', 'PL_surface_temp'
)

# Live read-only POC allowlist. The 2026-08-19 panel correlation contradicted
# several semantic candidates, and offline replay showed that the old TC2/TC3
# pair could create a false sensor-valid MT chamber and CRITICAL advisory. All
# Mod2 resources therefore stay under physical, unit-bearing audit names until
# a versioned mapping/quality profile is approved. Mod3 remains raw because the
# desktop VI's scaling is not known.
# No Mod1/Mod4 output resource can be supplied through a runtime argument.
$PspChannelAllowlist = [ordered]@{
    scan_Mod2_TC0_degC       = 'Mod2/TC0'
    scan_Mod2_TC1_degC       = 'Mod2/TC1'
    scan_Mod2_TC2_degC       = 'Mod2/TC2'
    scan_Mod2_TC3_degC       = 'Mod2/TC3'
    scan_Mod2_TC4_degC       = 'Mod2/TC4'
    scan_Mod2_TC5_degC       = 'Mod2/TC5'
    scan_Mod2_TC6_degC       = 'Mod2/TC6'
    scan_Mod2_TC7_degC       = 'Mod2/TC7'
    scan_Mod3_AI0_raw        = 'Mod3/AI0'
    scan_Mod3_AI1_raw        = 'Mod3/AI1'
    scan_Mod3_AI2_raw        = 'Mod3/AI2'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
$Readers = [ordered]@{}
$Latest = [ordered]@{}
$TcpClient = $null
$TcpStream = $null
$FramesSent = 0
$Mutex = [Threading.Mutex]::new($false, 'Global\RECLAIM-CrioPspAdapter')
$HasMutex = $false

function Test-FiniteScalar {
    param([Parameter(Mandatory = $true)]$Value)
    if ($Value -is [bool]) { return $true }
    if ($Value -isnot [sbyte] -and $Value -isnot [byte] -and
        $Value -isnot [int16] -and $Value -isnot [uint16] -and
        $Value -isnot [int32] -and $Value -isnot [uint32] -and
        $Value -isnot [int64] -and $Value -isnot [uint64] -and
        $Value -isnot [single] -and $Value -isnot [double] -and
        $Value -isnot [decimal]) { return $false }
    $Number = [double]$Value
    return -not ([double]::IsNaN($Number) -or [double]::IsInfinity($Number))
}

function ConvertTo-LineBytes {
    param([Parameter(Mandatory = $true)][Collections.IDictionary]$Frame)
    $Json = $Frame | ConvertTo-Json -Depth 5 -Compress
    if ($Json.Contains("`r") -or $Json.Contains("`n")) {
        throw 'serialized JSON unexpectedly contains a literal line break'
    }
    $Payload = $Utf8NoBom.GetBytes($Json)
    if (($Payload.Length + 1) -gt $MaxLineBytes) {
        throw "frame is $($Payload.Length + 1) bytes; limit is $MaxLineBytes"
    }
    $Line = [byte[]]::new($Payload.Length + 1)
    [Array]::Copy($Payload, $Line, $Payload.Length)
    $Line[$Line.Length - 1] = 0x0A
    return ,$Line
}

function New-EngineeringFrame {
    param(
        [Parameter(Mandatory = $true)][Collections.IDictionary]$Variables,
        [Parameter(Mandatory = $true)][datetime]$CapturedAt
    )
    $Typed = [ordered]@{}
    foreach ($Name in $Variables.Keys) {
        $Allowed = if ($Source -eq 'Psp') {
            $PspChannelAllowlist.Contains($Name)
        } else {
            $FixtureAllowlist -contains $Name
        }
        if (-not $Allowed) {
            throw "fixture/source field '$Name' is not in the POC allowlist"
        }
        $Value = $Variables[$Name]
        if (-not (Test-FiniteScalar -Value $Value)) {
            throw "field '$Name' is not a finite numeric/boolean scalar"
        }
        # Preserve typed scalars and exact zero. Current PSP sensor candidates
        # are doubles; retaining booleans here prevents future readbacks from
        # silently becoming 1.0/0.0.
        if ($Value -is [bool]) { $Typed[$Name] = [bool]$Value }
        else { $Typed[$Name] = [double]$Value }
    }
    return [ordered]@{
        source_id       = if ($Source -eq 'Psp') { 'reclaim-crio-scan-poc' } else { 'reclaim-crio-psp-poc' }
        cycle_id        = 'ENGINEERING-POC-NO-AUTHORITATIVE-CYCLE'
        ts              = $CapturedAt.ToUniversalTime().ToString('o')
        # Contract-valid engineering assumption for downstream POC only. This
        # is not represented as an authoritative cRIO sequencer observation.
        source_op_state = 'S_Idle'
        active_chamber  = 'NONE'
        vars            = $Typed
    }
}

function Open-PspReaders {
    if ([IntPtr]::Size -ne 4) {
        throw 'NI DataSocket is 32-bit; launch this script with SysWOW64 Windows PowerShell'
    }
    foreach ($Entry in $PspChannelAllowlist.GetEnumerator()) {
        $Reader = New-Object -ComObject CWDSLib.CWDataSocket
        $Reader.ClientBufferMaxPackets = 1
        $Reader.ClientBufferMaxBytes = 4096
        $Url = "psp://$CrioHost/$($Entry.Value)"
        # CWDS access mode 2 is cwdsRead. It is read-only; this adapter never
        # calls SyncWrite, Update in a write mode, or a CWData setter.
        # CWDataSocket can return False even when a read subscription succeeds
        # (LastError 0, "Active:Subscription successful."). Treat LastError as
        # the connection result; the first SyncRead plus the metadata/type
        # checks below establish that the requested item actually exists.
        $null = $Reader.SyncConnectTo($Url, 2, $FreshnessMs)
        if ($Reader.LastError -ne 0) {
            $Code = $Reader.LastError
            $Message = $Reader.LastMessage
            try { $Reader.Disconnect() } catch {}
            try { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($Reader) | Out-Null } catch {}
            throw "PSP connect '$($Entry.Key)' failed: $Code $Message"
        }
        $Readers[$Entry.Key] = $Reader
        if ($ConnectSpacingMs -gt 0) {
            Start-Sleep -Milliseconds $ConnectSpacingMs
        }
    }
}

function Close-PspReaders {
    foreach ($Reader in @($Readers.Values)) {
        try { $Reader.Disconnect() } catch {}
        try { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($Reader) | Out-Null } catch {}
    }
    $Readers.Clear()
    $Latest.Clear()
}

function Close-TcpConnection {
    if ($null -ne $script:TcpStream) {
        try { $script:TcpStream.Dispose() } catch {}
    }
    if ($null -ne $script:TcpClient) {
        try { $script:TcpClient.Dispose() } catch {}
    }
    $script:TcpStream = $null
    $script:TcpClient = $null
}

function Read-PspSnapshot {
    $Deadline = [datetime]::UtcNow.AddMilliseconds($FreshnessMs)
    do {
        foreach ($Name in $Readers.Keys) {
            $Reader = $Readers[$Name]
            # Console PowerShell does not pump ActiveX update events reliably.
            # SyncRead explicitly retrieves the current value while preserving
            # the read-only access mode of the already-open connection.
            $ReadOk = $Reader.SyncRead([Math]::Min(500, $FreshnessMs))
            if ($Reader.LastError -ne 0) {
                throw "PSP reader '$Name' failed: $($Reader.LastError) $($Reader.LastMessage)"
            }
            if ($ReadOk) {
                $Value = $Reader.Data.Value
                $AttributeNames = @($Reader.Data.GetAttributeNames())
                if ($AttributeNames.Count -eq 0) {
                    throw "PSP field '$Name' returned no NI metadata; refusing a possible default/nonexistent item"
                }
                if ($Value -isnot [single] -and $Value -isnot [double]) {
                    throw "PSP field '$Name' returned $($Value.GetType().FullName), not a floating-point scan value"
                }
                if (-not (Test-FiniteScalar -Value $Value)) {
                    throw "PSP field '$Name' is not a finite numeric/boolean scalar"
                }
                $Latest[$Name] = [pscustomobject]@{
                    Value = $Value
                    Seen  = [datetime]::UtcNow
                }
            }
        }
        if ($Latest.Count -eq $PspChannelAllowlist.Count) { break }
        Start-Sleep -Milliseconds 20
    } while ([datetime]::UtcNow -lt $Deadline)

    if ($Latest.Count -ne $PspChannelAllowlist.Count) {
        $Missing = @($PspChannelAllowlist.Keys | Where-Object { -not $Latest.Contains($_) })
        throw "PSP snapshot incomplete; no fresh value for: $($Missing -join ', ')"
    }
    $Now = [datetime]::UtcNow
    $Seen = @($Latest.Values | ForEach-Object { $_.Seen })
    $Oldest = ($Seen | Measure-Object -Minimum).Minimum
    $Newest = ($Seen | Measure-Object -Maximum).Maximum
    if (($Now - $Oldest).TotalMilliseconds -gt $FreshnessMs) {
        throw 'PSP snapshot contains a stale value'
    }
    if (($Newest - $Oldest).TotalMilliseconds -gt $MaxSkewMs) {
        throw "PSP snapshot skew exceeds $MaxSkewMs ms"
    }
    $Vars = [ordered]@{}
    foreach ($Name in $PspChannelAllowlist.Keys) {
        $Vars[$Name] = $Latest[$Name].Value
    }
    return New-EngineeringFrame -Variables $Vars -CapturedAt $Newest
}

function Read-FixtureFrame {
    if (-not $FixturePath) { throw '-FixturePath is required for Fixture source' }
    $Fixture = Get-Content -Raw -LiteralPath $FixturePath | ConvertFrom-Json
    $Vars = [ordered]@{}
    foreach ($Property in $Fixture.vars.psobject.Properties) {
        $Vars[$Property.Name] = $Property.Value
    }
    $CapturedAt = [datetime]::UtcNow
    if ($null -ne $Fixture.psobject.Properties['observed_at']) {
        $Observed = @{}
        foreach ($Property in $Fixture.observed_at.psobject.Properties) {
            $Observed[$Property.Name] = [datetime]::Parse($Property.Value).ToUniversalTime()
        }
        $Missing = @($Vars.Keys | Where-Object { -not $Observed.ContainsKey($_) })
        if ($Missing.Count -gt 0) {
            throw "fixture has no observation timestamp for: $($Missing -join ', ')"
        }
        $Times = @($Vars.Keys | ForEach-Object { $Observed[$_] })
        $Oldest = ($Times | Measure-Object -Minimum).Minimum
        $CapturedAt = ($Times | Measure-Object -Maximum).Maximum
        if (([datetime]::UtcNow - $Oldest).TotalMilliseconds -gt $FreshnessMs) {
            throw 'fixture snapshot contains a stale value'
        }
        if (($CapturedAt - $Oldest).TotalMilliseconds -gt $MaxSkewMs) {
            throw "fixture snapshot skew exceeds $MaxSkewMs ms"
        }
    }
    return New-EngineeringFrame -Variables $Vars -CapturedAt $CapturedAt
}

function Write-Frame {
    param([Parameter(Mandatory = $true)][byte[]]$Line)
    if ($Sink -eq 'File') {
        if (-not $OutputPath) { throw '-OutputPath is required for File sink' }
        $Stream = [IO.File]::Open($OutputPath, [IO.FileMode]::Append,
            [IO.FileAccess]::Write, [IO.FileShare]::Read)
        try { $Stream.Write($Line, 0, $Line.Length); $Stream.Flush() }
        finally { $Stream.Dispose() }
        return
    }
    if ($null -eq $script:TcpClient -or -not $script:TcpClient.Connected) {
        if ($null -ne $script:TcpStream) { $script:TcpStream.Dispose() }
        if ($null -ne $script:TcpClient) { $script:TcpClient.Dispose() }
        $script:TcpClient = [Net.Sockets.TcpClient]::new()
        $Connect = $script:TcpClient.ConnectAsync($GatewayHost, $GatewayPort)
        if (-not $Connect.Wait(3000)) { throw 'gateway TCP connect timed out' }
        $script:TcpStream = $script:TcpClient.GetStream()
        $script:TcpStream.WriteTimeout = 3000
    }
    try {
        $script:TcpStream.Write($Line, 0, $Line.Length)
        $script:TcpStream.Flush()
    } catch {
        Close-TcpConnection
        throw # Current snapshot is discarded; callers never replay it.
    }
}

try {
    $HasMutex = $Mutex.WaitOne(0)
    if (-not $HasMutex) { throw 'another RECLAIM cRIO PSP adapter instance is running' }
    do {
        try {
            $Started = [datetime]::UtcNow
            if ($Source -eq 'Psp') {
                if ($Readers.Count -eq 0) { Open-PspReaders }
                $Frame = Read-PspSnapshot
            } else {
                $Frame = Read-FixtureFrame
            }
            $Line = ConvertTo-LineBytes -Frame $Frame
            Write-Frame -Line $Line
            $FramesSent++
            if ($MaxFrames -gt 0 -and $FramesSent -ge $MaxFrames) { break }
            $Remaining = $CadenceMs - [int]([datetime]::UtcNow - $Started).TotalMilliseconds
            if ($Remaining -gt 0) { Start-Sleep -Milliseconds $Remaining }
        } catch {
            # Only explicitly requested live PSP mode reconnects forever. The
            # failed snapshot is discarded, all latest values are cleared, and
            # the next attempt opens fresh read-only subscriptions and a fresh
            # TCP connection. Fixture and bounded runs remain fail-fast tests.
            if ($Source -ne 'Psp' -or $MaxFrames -ne 0) { throw }
            Write-Warning "adapter iteration failed; discarded snapshot; retrying in $ReconnectDelayMs ms: $($_.Exception.Message)"
            Close-PspReaders
            Close-TcpConnection
            Start-Sleep -Milliseconds $ReconnectDelayMs
        }
    } while ($true)
} finally {
    Close-PspReaders
    Close-TcpConnection
    if ($HasMutex) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
