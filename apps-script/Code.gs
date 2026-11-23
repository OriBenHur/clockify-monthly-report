var SCHEDULER_HOUR = 9;

function scheduleLastDayTrigger() {
  assertJerusalem_();
  clearHandler_('scheduleLastDayTrigger');
  var now = new Date();
  var nextRun = firstOfNextMonth(now);
  ScriptApp.newTrigger('scheduleLastDayTrigger').timeBased().at(nextRun).create();
  Logger.log('Scheduler scheduled for ' + nextRun);

  clearHandler_('sendWebhookToMake');
  var slot = reminderSlot(
    now.getFullYear(),
    now.getMonth(),
    loadYomTov_(now.getFullYear(), now.getMonth())
  );
  if (slot.getTime() <= now.getTime()) {
    Logger.log('Reminder time already passed: ' + slot);
    return;
  }
  ScriptApp.newTrigger('sendWebhookToMake').timeBased().at(slot).create();
  Logger.log('Reminder scheduled for ' + slot);
}

function sendWebhookToMake() {
  assertJerusalem_();
  var scriptProperties = PropertiesService.getScriptProperties();
  var url = scriptProperties.getProperty('MAKE_URL');
  var mySecretToken = scriptProperties.getProperty('MAKE_TOKEN');

  if (!url || !mySecretToken) {
    throw new Error('Missing configuration properties.');
  }

  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + mySecretToken
    },
    payload: JSON.stringify({ trigger: 'end_of_month' })
  };

  UrlFetchApp.fetch(url, options);
}

function firstOfNextMonth(from) {
  return new Date(from.getFullYear(), from.getMonth() + 1, 1, SCHEDULER_HOUR, 0, 0, 0);
}

function reminderSlot(year, monthIndex, yomTov) {
  var day = new Date(year, monthIndex + 1, 0, 12, 0, 0, 0);
  while (isRest_(day, yomTov)) {
    day.setDate(day.getDate() - 1);
  }
  if (day.getDay() === 5) {
    day.setDate(day.getDate() - 1);
    while (isRest_(day, yomTov)) {
      day.setDate(day.getDate() - 1);
    }
    if (day.getDay() === 5) {
      day.setDate(day.getDate() - 1);
      return atTime_(day, 19, 0);
    }
    if (isErevChag_(day, yomTov)) {
      return atTime_(day, 15, 0);
    }
    return atTime_(day, 19, 0);
  }
  if (isErevChag_(day, yomTov)) {
    return atTime_(day, 15, 0);
  }
  return atTime_(day, 19, 0);
}

function yomTovFromHebcal(body) {
  var data = JSON.parse(body);
  var set = {};
  var items = data.items || [];
  for (var i = 0; i < items.length; i++) {
    if (items[i].yomtov) {
      set[String(items[i].date).substring(0, 10)] = true;
    }
  }
  return set;
}

function isRest_(date, yomTov) {
  return date.getDay() === 6 || !!yomTov[dayKey_(date)];
}

function isErevChag_(date, yomTov) {
  var next = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1, 12, 0, 0, 0);
  return !!yomTov[dayKey_(next)];
}

function atTime_(date, hour, minute) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), hour, minute, 0, 0);
}

function dayKey_(date) {
  var month = date.getMonth() + 1;
  var day = date.getDate();
  return date.getFullYear() + '-' + (month < 10 ? '0' + month : month) + '-' + (day < 10 ? '0' + day : day);
}

function hebcalRange_(year, monthIndex) {
  var start = new Date(year, monthIndex, 1, 12, 0, 0, 0);
  start.setDate(start.getDate() - 7);
  var end = new Date(year, monthIndex + 1, 2, 12, 0, 0, 0);
  return dayKey_(start) + '/' + dayKey_(end);
}

function loadYomTov_(year, monthIndex) {
  var range = hebcalRange_(year, monthIndex).split('/');
  var url = 'https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&i=on&geo=none'
    + '&start=' + range[0] + '&end=' + range[1];
  var response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  if (response.getResponseCode() !== 200) {
    throw new Error('Hebcal request failed: ' + response.getResponseCode());
  }
  return yomTovFromHebcal(response.getContentText());
}

function assertJerusalem_() {
  var tz = Session.getScriptTimeZone();
  if (tz !== 'Asia/Jerusalem') {
    throw new Error('Script timezone must be Asia/Jerusalem, got ' + tz);
  }
}

function clearHandler_(name) {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === name) {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
}
