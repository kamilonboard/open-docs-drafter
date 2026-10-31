import SwiftUI

struct DecimalPickerSettings {
    var maxIOB = PickerSetting(value: 0, step: 1, min: 0, max: 30, type: PickerSetting.PickerSettingType.insulinUnit)
    var maxSMBBasalMinutes = PickerSetting(value: 30, step: 5, min: 15, max: 180, type: PickerSetting.PickerSettingType.minute)
    var smbInterval = PickerSetting(value: 3, step: 1, min: 1, max: 10, type: PickerSetting.PickerSettingType.minute)
    var maxBasal = PickerSetting(
        value: 10,
        step: 0.5,
        min: 0.5,
        max: 30,
        type: PickerSetting.PickerSettingType.insulinUnitPerHour
    )
    var maxDailySafetyMultiplier = PickerSetting(
        value: 3,
        step: 0.1,
        min: 1,
        max: 5, // upper bound
        type: PickerSetting.PickerSettingType.factor
    )
}
