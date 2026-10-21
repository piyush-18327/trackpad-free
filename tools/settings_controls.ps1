# Bounded UI Automation inspection. Invocations are always explicit and target
# an AutomationId observed in the Settings window; no blind screen clicks.
param([string]$Id = '', [string]$Action = '', [string]$Value = '', [string]$Group = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$window = $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
    [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty, 'Settings'))
if (-not $window) { throw 'Open Windows Settings > Bluetooth & devices > Touchpad first.' }
if ($Id) {
    $scope = $window
    if ($Group) {
        $scope = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.AndCondition]::new(
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty, $Group),
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Group)))
        if (-not $scope) { throw "Group not found: $Group" }
        $pattern = $null
        if ($scope.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$pattern)) { $pattern.ScrollIntoView() }
    }
    $element = $scope.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $Id))
    if (-not $element -and $Group) {
        $expander = $scope.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'EntityItemButton'))
        $expander.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
        for ($i=0; $i -lt 20 -and -not $element; $i++) {
            Start-Sleep -Milliseconds 50
            $element = $scope.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $Id))
        }
    }
    if (-not $element) { throw "Control not found: $Id" }
    $scroll = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$scroll)) { $scroll.ScrollIntoView() }
    switch ($Action) {
        'expand' { $element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() }
        'invoke' { $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
        'select' { $element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() }
        'toggle' { $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle() }
        'choose' {
            $element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
            $option = $element.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty, $Value))
            if (-not $option) { throw "Option not found: $Value" }
            $option.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        }
        default { throw 'Specify expand, invoke, select, or toggle.' }
    }
}
$window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) |
    Where-Object { -not $_.Current.IsOffscreen -and $_.Current.Name -and $_.Current.ControlType -in @([System.Windows.Automation.ControlType]::ComboBox, [System.Windows.Automation.ControlType]::ListItem, [System.Windows.Automation.ControlType]::CheckBox) } |
    ForEach-Object { [pscustomobject]@{ Name=$_.Current.Name; Id=$_.Current.AutomationId; Type=$_.Current.ControlType.ProgrammaticName } } |
    ConvertTo-Json -Depth 3
