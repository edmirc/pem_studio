# PEM Studio - abre o arquivo 3D (ou a pasta dele) a partir do sistema.
# Chamado pelo navegador com links "pemstudio:pasta?p=..." e "pemstudio:abrir?com=...&p=...".
param([string]$Url)

# ---- Ajuste aqui se precisar ------------------------------------------------
# Caminho dos fatiadores (deixe vazio para o script procurar sozinho)
$CrealityPrint = ''
$BambuStudio   = ''
$SnapmakerOrca = ''
# Caminhos do servidor Linux que viram caminho de rede no Windows
$Mapas = @{
    '/mnt/hd4t' = '\\192.168.3.190\hd4t'
}
# -----------------------------------------------------------------------------

$Extensoes3D = @('.3mf', '.stl', '.obj', '.step', '.stp', '.amf', '.ply', '.gcode', '.bgcode')
Add-Type -AssemblyName System.Windows.Forms

function Aviso([string]$texto) {
    [System.Windows.Forms.MessageBox]::Show($texto, 'PEM Studio', 'OK', 'Warning') | Out-Null
}

function Ler-Parametros([string]$q) {
    $r = @{}
    foreach ($par in $q.Split('&')) {
        $i = $par.IndexOf('=')
        if ($i -gt 0) { $r[$par.Substring(0, $i)] = [uri]::UnescapeDataString($par.Substring($i + 1)) }
    }
    return $r
}

function Achar-Programa([string]$fixo, [string[]]$pastas, [string]$exe) {
    if ($fixo -and (Test-Path -LiteralPath $fixo)) { return $fixo }
    foreach ($p in $pastas) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            # o programa principal é o maior .exe da pasta (ignora desinstalador e utilitários)
            $achado = Get-ChildItem -LiteralPath $p -Filter $exe -Recurse -Depth 2 -ErrorAction SilentlyContinue |
                      Where-Object { $_.Name -notmatch 'unins|uninstall|validator|crash|helper|update' } |
                      Sort-Object Length -Descending | Select-Object -First 1
            if ($achado) { return $achado.FullName }
        }
    }
    return $null
}

if ($Url -notmatch '^pemstudio:(?://)?([a-z]+)/?\?(.*)$') { Aviso "Link inválido:`n$Url"; exit 1 }
$acao = $Matches[1]
$par = Ler-Parametros $Matches[2]
$caminho = ("" + $par['p']).Trim().Trim('"').Trim()
if (-not $caminho) { Aviso 'O produto não tem caminho de arquivo.'; exit 1 }

foreach ($k in $Mapas.Keys) {
    if ($caminho.StartsWith($k)) { $caminho = $Mapas[$k] + $caminho.Substring($k.Length); break }
}
if ($caminho.StartsWith('//') -or $caminho -match '^[A-Za-z]:/') { $caminho = $caminho.Replace('/', '\') }

if (-not (Test-Path -LiteralPath $caminho)) {
    $pasta = Split-Path -Path $caminho -Parent
    if ($pasta -and (Test-Path -LiteralPath $pasta)) {
        Aviso "Não achei o arquivo:`n$caminho`n`nVou abrir a pasta onde ele deveria estar."
        Start-Process explorer.exe -ArgumentList "`"$pasta`""
    } else {
        Aviso "Não achei o arquivo nem a pasta:`n$caminho`n`nConfira se o servidor está ligado e se o caminho está certo."
    }
    exit 1
}

$item = Get-Item -LiteralPath $caminho
if ($acao -eq 'pasta') {
    if ($item.PSIsContainer) { Start-Process explorer.exe -ArgumentList "`"$caminho`"" }
    else { Start-Process explorer.exe -ArgumentList "/select,`"$caminho`"" }
    exit 0
}

if ($acao -ne 'abrir') { Aviso "Ação desconhecida: $acao"; exit 1 }
if ($item.PSIsContainer) { Start-Process explorer.exe -ArgumentList "`"$caminho`""; exit 0 }
if ($Extensoes3D -notcontains $item.Extension.ToLower()) {
    # Por segurança só abre arquivos 3D; qualquer outro tipo só mostra na pasta.
    Start-Process explorer.exe -ArgumentList "/select,`"$caminho`""
    exit 0
}

$pf = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")
$programa = $null
switch ($par['com']) {
    'creality' { $programa = Achar-Programa $CrealityPrint ($pf | ForEach-Object { if ($_) { Join-Path $_ 'Creality' } }) 'CrealityPrint.exe'
                 $nomeProg = 'Creality Print' }
    'bambu'    { $programa = Achar-Programa $BambuStudio ($pf | ForEach-Object { if ($_) { Join-Path $_ 'Bambu Studio' } }) 'bambu-studio.exe'
                 $nomeProg = 'Bambu Studio' }
    'snapmaker' { $pastasSM = foreach ($b in $pf) { if ($b) { foreach ($n in @('snapmaker_orca', 'Snapmaker Orca', 'Snapmaker_Orca', 'Snapmaker Orca Slicer')) { Join-Path $b $n } } }
                  $programa = Achar-Programa $SnapmakerOrca $pastasSM '*.exe'
                  $nomeProg = 'Snapmaker Orca' }
}
if ($programa) {
    Start-Process -FilePath $programa -ArgumentList "`"$caminho`""
} else {
    if ($par['com'] -in @('creality', 'bambu', 'snapmaker')) {
        Aviso "Não achei o $nomeProg neste computador. Vou abrir com o programa padrão do Windows.`n`n(Se ele estiver instalado em outro lugar, coloque o caminho no começo do arquivo abrir.ps1.)"
    }
    Invoke-Item -LiteralPath $caminho
}
