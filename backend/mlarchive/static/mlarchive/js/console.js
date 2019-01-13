/* console.js */

$(function() {
    Highcharts.chart('weekly-chart', window.weeklyChartConf);
    Highcharts.chart('top25-chart', window.top25ChartConf);
});