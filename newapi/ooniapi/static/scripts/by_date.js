import * as d3 from "d3";
import moment from "moment";


function chart(element, chartData, fromDate, toDate) {

  let CHART_WIDTH = 550;
  let CHART_HEIGHT = 80;
  let SQUARE_LENGTH = 8;
  let SQUARE_PADDING = 2;

  let weekStart = 0; // 0 sunday 1 monday

  let max = d3.max(chartData.slice(-30), (d) => {
    return d.count
  });

  let dateRange = d3.timeDays(fromDate, toDate);
  let firstDate = moment(dateRange[0]);

  let color = d3.scaleLinear()
    .range(['#07ACFF', '#034C70'])
    .domain([0, max]);
  let tooltip;
  let dayRects;

  drawChart();

  function drawChart() {
    let daysOfChart = {};

    chartData.forEach((d) => {
      daysOfChart[moment(d.date).format("YYYY-MM-DD")] = d.count;
    });

    let svg = element
      .append('svg')
      .attr('width', CHART_WIDTH)
      .attr('height', CHART_HEIGHT);

    dayRects = svg.selectAll('.cell')
      .data(dateRange);

    dayRects.enter().append('rect')
      .attr('class', 'cell')
      .attr('width', SQUARE_LENGTH)
      .attr('height', SQUARE_LENGTH)
      .attr('fill', (d, i) => {
        let count = daysOfChart[moment(d).format("YYYY-MM-DD")];
        if (count === undefined) {
          return 'grey';
        } else {
          return color(count);
        }
      })
      .attr('x', (d) => {
        let cellDate = moment(d);
        let result = cellDate.week() - firstDate.week() + (firstDate.weeksInYear() * (cellDate.weekYear() - firstDate.weekYear()));
        return result * (SQUARE_LENGTH + SQUARE_PADDING);
      })
      .attr('y', (d) => {
        return formatWeekday(d.getDay()) * (SQUARE_LENGTH + SQUARE_PADDING);
      })
      .on('mouseover', (d, i) => {
        tooltip = element
          .append('div')
          .attr('class', 'cell-tooltip')
          .html(tooltipHTML(getDataOnDay(d)))
          .style('left', (Math.floor(i / 7) * SQUARE_LENGTH + 'px'))
          .style('top', formatWeekday(d.getDay()) * (SQUARE_LENGTH + SQUARE_PADDING));
      }).on('mouseout', (d, i) => {
        tooltip.remove();
      }).on('click', (d, i) => {
        if (opener !== null) {
          opener.remove();
          opener = null;
        }
        opener = element
          .append('a')
          .attr('class', 'btn date-opener')
          .attr('href', '/files/by_date/' + moment(d).format('YYYY-MM-DD'))
          .style('left', 100)
          .style('top', 22)
          .text('Open ' + moment(d).format('YYYY-MM-DD'));
      });

    dayRects.exit().remove();

    function tooltipHTML(data) {
      var dateStr = moment(data.date).format('ddd, MMM Do YYYY');
      return "<strong>" + dateStr + "</strong>: " + data.count;
    }

    function formatWeekday(weekDay) {
      if (weekStart === 1) {
        if (weekDay === 0) {
          return 6;
        } else {
          return weekDay - 1;
        }
      }
      return weekDay;
    }

    function getDataOnDay(day) {
      let data = daysOfChart[moment(day).format("YYYY-MM-DD")];
      if (data === undefined) {
        data = 0;
      }
      return {
        'date': day,
        'count': data
      };
    }
  }
}

d3.select('.no-js-warning').classed('hidden', true);
d3.select('.loading').classed('hidden', false);

d3.json('/api/_/reports_per_day', (chartData) => {
  let ooniEpoch = moment('2012-01-01').toDate();
  let now = moment().endOf('day').toDate();

  let calendar = d3.select('.calendars');

  let dayParse = d3.timeParse("%Y-%m-%d");

  chartData.forEach((d) => {
    d.date = dayParse(d.date);
  });

  d3.utcYears(ooniEpoch, now).forEach((fromDate) => {
    let toDate = moment(fromDate).endOf('year').toDate();
    if (toDate > now){
      toDate = now;
    }
    let element = calendar.append('div')
      .attr('class', 'col-md-6');
    element.append('h2')
      .text(moment(fromDate).format('YYYY'));
    chart(element, chartData, fromDate, toDate);
  });

  d3.select('.loading').classed('hidden', true);

});
