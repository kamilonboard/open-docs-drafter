import SwiftUI

struct SMBSettingsRootView: View {
    var body: some View {
        List {
            SettingInputSection(
                decimalValue: $decimalPlaceholder,
                booleanValue: $state.enableSMBAlways,
                units: state.units,
                type: .boolean,
                label: String(localized: "Enable SMB Always", comment: "Enable SMB Always"),
                miniHint: String(localized: "Allow SMBs at all times except when a high Temp Target is set."),
                verboseHint: VStack {
                    Text("Default: OFF").bold()
                    Text("When enabled, Super Micro Boluses (SMBs) will always be allowed.")
                }
            )

            SettingInputSection(
                decimalValue: $state.maxSMBBasalMinutes,
                booleanValue: $booleanPlaceholder,
                units: state.units,
                type: .decimal("maxSMBBasalMinutes"),
                label: String(localized: "Max SMB Basal Minutes", comment: "Max SMB Basal Minutes"),
                verboseHint: VStack {
                    Text("Default: 30 minutes").bold()
                }
            )

            SettingInputSection(
                decimalValue: $state.smbInterval,
                booleanValue: $booleanPlaceholder,
                units: state.units,
                type: .decimal("smbInterval"),
                label: String(localized: "SMB Delivery Interval"),
                verboseHint: VStack {
                    Text("Default: 5 min").bold()
                }
            )
        }
    }
}
