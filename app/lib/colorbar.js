var script = document.createElement('script');
script.type = 'text/javascript';
script.src = 'https://cdnjs.cloudflare.com/ajax/libs/svg.js/3.2.0/svg.min.js';
document.head.appendChild(script);

var svgelem=document.querySelectorAll('svg.main-svg')[1]
var svgobj=SVG(svgelem)
var gradient=svgobj.gradient('linear', function(add) {
  add.stop(0, '#333')
  add.stop(1, '#fff')
})
gradient.from(0, 1).to(0, 0)
fillurl=gradient.url()

elem=document.querySelector('.infolayer .cbfills rect')
document.querySelector('.infolayer .cbfills rect')
var obj = SVG(elem)
obj.attr({style:'pointer-events:all'})
obj.attr({ fill: gradient })


