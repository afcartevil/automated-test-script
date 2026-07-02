# FixGpioOrder.ps1 - Fix GPIO order in DWS file and copy configurations from source
param(
    [Parameter(Mandatory=$true)]
    [string]$SourcePath,

    [Parameter(Mandatory=$true)]
    [string]$TargetPath,

    [Parameter(Mandatory=$true)]
    [string]$GpioList
)

$gpiosToProcess = $GpioList -split "," | ForEach-Object { [int]$_ } | Sort-Object

$sourceContent = Get-Content -Path $SourcePath -Raw
$targetContent = Get-Content -Path $TargetPath -Raw

# Step 1: Delete existing GPIO configs in target for these GPIOs
foreach ($gpioNum in $gpiosToProcess) {
    $pattern = "<gpio$gpioNum>[\s\S]*?</gpio$gpioNum>`n?"
    $targetContent = $targetContent -replace $pattern, ""
    Write-Output "Removed existing GPIO$gpioNum config from target"
}

# Step 2: Re-insert in numerical order
foreach ($gpioNum in $gpiosToProcess) {
    $sourcePattern = "<gpio$gpioNum>([\s\S]*?)</gpio$gpioNum>"
    $sourceMatch = [regex]::Match($sourceContent, $sourcePattern)

    if ($sourceMatch.Success) {
        $gpioConfig = $sourceMatch.Groups[1].Value

        $allGpioPattern = "<gpio(\d+)>"
        $allGpioMatches = [regex]::Matches($targetContent, $allGpioPattern)
        $existingGpioNums = $allGpioMatches | ForEach-Object { [int]$_.Groups[1].Value } | Sort-Object

        $insertBeforeGpio = $null
        foreach ($existingNum in $existingGpioNums) {
            if ($existingNum -gt $gpioNum) {
                $insertBeforeGpio = $existingNum
                break
            }
        }

        $newGpioBlock = "`n<gpio$gpioNum>$gpioConfig</gpio$gpioNum>"

        if ($insertBeforeGpio) {
            $insertPattern = "<gpio$insertBeforeGpio>"
            $targetContent = $targetContent.Replace($insertPattern, "$newGpioBlock`n$insertPattern")
            Write-Output "Inserted GPIO$gpioNum before GPIO$insertBeforeGpio"
        } else {
            $targetContent = $targetContent + "`n" + $newGpioBlock
            Write-Output "Inserted GPIO$gpioNum at end of file"
        }
    } else {
        Write-Warning "Could not find GPIO$gpioNum config in source file"
    }
}

Set-Content -Path $TargetPath -Value $targetContent -NoNewline
Write-Output "DWS file GPIO order fix complete"
