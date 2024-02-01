<svg viewBox="0 0 {{x2 + 100}} {{y2}}" version="1.1" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns="http://www.w3.org/2000/svg">
  <style>
.txt { font: 13px sans-serif }
.dot {
  stroke-opacity: .2;
}
  body svg {
    width: 99%;
    height: 40em;
  }
  svg g#msmts circle {
    border: 1px solid #888;
    stroke: #606060;
    stroke-width: .5px;
    opacity: 0.2;
  }
  line.change {
    stroke-width: 4px;
    opacity: 0.2;
  }
  </style>
  <text x="{{x1+100}}" y="20" class="txt">{{cc}} {{test_name}} {{inp}}</text>
  <g id="msmts">
  % pcx = pcy = None
  % for d, val, mean in msmts:
  % cx = (d - start_d).total_seconds() * x_scale + x1
  % cy = y2 - min(max(val, 0) * 100, 300)
  % r = "{:02x}".format(min(int(max(val, 0) * 170), 255))
  <circle class="dot" style="fill:#{{r}}ff00;" cx="{{cx}}" cy="{{cy}}"
                                                           r="4"></circle>

  % # moving average
  % cy = y2 - min(max(mean, 0) * 100, 300)
  % if pcy is not None:
  <line x1="{{pcx}}" x2="{{cx}}" y1="{{pcy}}" y2="{{cy}}" stroke="#d2eaff"></line>
  % end
  % pcx, pcy = cx, cy
  % end

  % # changes in blocking
  % for c in changes:
  %   cx = (c.measurement_start_time - start_d).total_seconds() * x_scale + x1
  %   col = "ff3333" if c.blocked else "33ff33"
  <line class="change" x1="{{cx}}" x2="{{cx}}" y1="{{y1 + 50}}" y2="{{y2}}" stroke="#{{col}}"></line>
  % end

  </g>
  <text x="{{x1-80}}" y="{{y2+30}}" class="txt">{{start_d}}</text>
  <text x="{{x2-80}}" y="{{y2+30}}" class="txt">{{d}}</text>

  <line x1="{{x1}}" x2="{{x2}}" y1="{{y2}}" y2="{{y2}}" stroke="#888"></line>
  <line x1="{{x1}}" x2="{{x1}}" y1="{{y1}}" y2="{{y2}}" stroke="#888"></line>

  % for val in (0.0, 1.0, 2.0):
  % cy = y2 - min(max(val, 0) * 100, (y2 - y1))
  <line x1="{{x1-5}}" x2="{{x1-10}}" y1="{{cy}}" y2="{{cy}}" stroke="#888"></line>
  % end
</svg>
