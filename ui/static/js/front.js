/*
Copyright 2009 Google Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

/**
 * @fileoverview
 * Controller for front.html, implementing a Google Maps API UI that queries
 * CAP data from the AlertFeed backend via Google Feeds API.  CAP messages are
 * converted to Maps Markers.
 *
 * @author api.roman.public@gmail.com (Roman Nurik)
 * @author Matthew.H.Frantz@gmail.com (Matt Frantz)
 */

/**
 * {google.maps.Gmap2} Google Maps API object representing the on-screen map.
 */
var map;

/**
 * jQuery Layout object (from jQuery Layout plugin) representing the page
 * layout.
 */
var pageLayout;

/**
 * Objects representing each alert, created by loadFeed.
 */
var alertItems = [];

/**
 * {string} Currently selected category.
 */
var selectedCategory;

/**
 * Associates an icon for each CAP category.
 */
var iconForCategory = {
  'Geo': '/static/images/marker-icons/climate/earthquake.png',
  'Met': '/static/images/marker-icons/climate/thunder.png',
  'Infra': '/static/images/marker-icons/aid-and-infrastructure/roads.png',
  // TODO(Matt Frantz): Add other categories.
};

/**
 * Handles changes to the category selector.
 */
function onChangeCategory() {
  var category = $('#category-select').val();
  if (!(selectedCategory && selectedCategory == category)) {
    selectedCategory = category;
    loadFeed();
  }
}

/**
 * Initializes the page.
 */
function initialize() {
  // set up page layout
  pageLayout = $('#container').layout({
    spacing_open: 0,
    resizable: false,
    closable: false,
    north__resizable: false,
    west__size: 250
  });

  $('#map-pane, #listview-pane').layout({
    spacing_open: 0,
    closable: 0,
    resizable: 0
  });

  // create map
  map = new google.maps.Map2($('#map').get(0));
  map.setCenter(new google.maps.LatLng(0, 0), 2);
  map.setUIToDefault();

  // create shadow screen overlays
  map.addOverlay(
      new google.maps.ScreenOverlay('/static/images/map-shadow-left.png',
      new google.maps.ScreenPoint(0, 1, 'fraction', 'fraction'),
      new google.maps.ScreenPoint(0, 1, 'fraction', 'fraction'),
      new google.maps.ScreenSize(4, 1, 'pixels', 'fraction')));
  map.addOverlay(
      new google.maps.ScreenOverlay('/static/images/map-shadow-top.png',
      new google.maps.ScreenPoint(0, 1, 'fraction', 'fraction'),
      new google.maps.ScreenPoint(0, 1, 'fraction', 'fraction'),
      new google.maps.ScreenSize(1, 4, 'fraction', 'pixels')));

  // Add the UI handlers.
  var categorySelect = $('#category-select');
  categorySelect.change(onChangeCategory);
  selectedCategory = categorySelect.val();

  loadFeed();
}

/**
 * Removes items from the map.
 * @param {list} alertItems List of objects created by loadFeed representing
 *     each feed item.  Only the overlays property is accessed.
 */
function clearItemsFromMap(alertItems) {
  for (var i in alertItems) {
    var alertItem = alertItems[i];
    var overlays = alertItem.overlays;
    for (var j in overlays) {
      var overlay = overlays[j];
      map.removeOverlay(overlay);
    }
    alertItem.overlays = [];
  }
}

/**
 * Adds an item to the list on the left-hand side containing only text.
 * @param {string} text Text to display.
 */
function addTextItem(text) {
  $('<li>')
      .append($('<span>').text(text))
      .appendTo($('#alert-list'));
}

/**
 * Loads the feed based on the current selections from the UI.
 */
function loadFeed() {
  // Display an indicator that we are loading something.
  $('#alert-list').html('<li><i>Loading</i></li>');

  // Remove any existing placemarks from the map.
  clearItemsFromMap(alertItems);
  alertItems = [];

  // init CAP feed
  var feed = new google.feeds.Feed(
      'http://gongo-dev.appspot.com/cap2atom?category=' + selectedCategory);
  feed.setResultFormat(google.feeds.Feed.MIXED_FORMAT);
  feed.setNumEntries(-1);
  feed.load(function(result) {
    $('#alert-list').html('');
    if (result.error) {
      // Something went wrong with the fetch.
      addTextItem(result.error.message);
    } else if (result.feed.entries.length == 0) {
      // No alerts were found.
      addTextItem('No alerts');
    } else {
      // Display the alerts that we found.
      for (var i = 0; i < result.feed.entries.length; i++) {
        var alertItem = {};

        var entry = result.feed.entries[i];
        alertItem.title = entry.title;
        alertItem.overlays = [];
        alertItem.cap = xmlNodeToJson(
            entry.xmlNode.getElementsByTagName('alert')[0]);
        alertItem.bounds = null;

        // Look at the info element(s).
        var infos = ('info' in alertItem.cap) ?
            listify(alertItem.cap.info) : [];
        for (var infoIdx in infos) {
          var info = infos[infoIdx];

          // Set the icon based on one of the categories.  There might be
          // several per info element, so just pick the first one.
          if ('category' in info) {
            var categories = listify(info.category);
            var category = categories[0].$t;
            alertItem.icon = iconForCategory[category];
          }

          // Make sure that the properties accessed by the microtemplates are
          // present.
          var properties = ['headline', 'description', 'web'];
          for (var propertyIdx in properties) {
            var property = properties[propertyIdx];
            if (!(property in info)) {
              info[property] = {'$t': ''};
            }
          }

          // Look at the area element(s).
          var areas = ('area' in info) ? listify(info.area) : [];
          for (var areaIdx in areas) {
            var area = areas[areaIdx];

            // Look at the circle element(s).
            var circles = ('circle' in area) ? listify(area.circle) : [];
            for (var circleIdx in circles) {
              var circle = circles[circleIdx];
              circleMatch = circle.$t.match(
                  /([\d\.\-]+),([\d\.\-]+)\s+([\d\.\-]+)/);
              var lat = parseFloat(circleMatch[1]);
              var lon = parseFloat(circleMatch[2]);
              var radius = parseFloat(circleMatch[3]) * 1000;  // convert to km

              var icon = new google.maps.Icon();
              icon.image = alertItem.icon;
              icon.iconSize = new google.maps.Size(32, 32);
              icon.iconAnchor = new google.maps.Point(16, 16);
              icon.infoWindowAnchor = new google.maps.Point(16, 16);

              var marker = new google.maps.Marker(
                  new google.maps.LatLng(lat, lon), { icon: icon });
              alertItem.overlays.push(marker);
              alertItem.bounds = new google.maps.LatLngBounds(
                  new google.maps.LatLng(lat, lon));

              if (radius) {
                var points = [];
                for (var heading = 0; heading <= 360; heading += 10) {
                  var point = new geo.Point(lat, lon).destination(
                      { heading: heading, distance: radius });
                  points.push(new google.maps.LatLng(point.lat(), point.lng()));
                }

                var polygon = new google.maps.Polygon(
                    points, '0000ff', 4, 1.0, '0000ff', 0.25);
                alertItem.overlays.push(polygon);
                alertItem.bounds = polygon.getBounds();
              }
            }
          }
        }

        // Add the overlays for this alert (already computed) to the map, and
        // make them clickable.
        for (var j = 0; j < alertItem.overlays.length; j++) {
          map.addOverlay(alertItem.overlays[j]);
          google.maps.Event.addListener(alertItem.overlays[j],
              'click', (function(fitem) {
                return function() {
                  selectAlertItem(fitem);
                  showAlertItemInfoWindow(fitem);
                };
              })(alertItem));
        }

        // Add the left-hand side alert.
        alertItem.listNode = $('<li>')
            .append($('<img class="icon">').attr('src', alertItem.icon))
            .append($('<span>').text(entry.title))
            .click((function(fitem) {
              return function() {
                selectAlertItem(fitem);
                showAlertItemInfoWindow(fitem);
                zoomToAlertItem(fitem);
              };
            })(alertItem))
            .get(0);
        $('#alert-list').append(alertItem.listNode);

        // Save the alert data for later, since we'll need it to clear the map.
        alertItems.push(alertItem);
      }
    }
  });
}

/**
 * Handles clicking on the map overlay.
 * @param {object} alertItem One of the objects created in loadFeed
 *     representing a single alert.
 */
function selectAlertItem(alertItem) {
  $('#alert-list li').removeClass('selected');
  $(alertItem.listNode).addClass('selected');
}

/**
 * Repositions the map based on the bounds of a single alert.
 * @param {object} alertItem One of the objects created in loadFeed
 *     representing a single alert.
 */
function zoomToAlertItem(alertItem) {
  if (alertItem.bounds) {
    map.setCenter(alertItem.bounds.getCenter(),
        map.getBoundsZoomLevel(alertItem.bounds));
  }
}

/**
 * Displays the bubble in the map on the selected alert.
 * @param {object} alertItem One of the objects created in loadFeed
 *     representing a single alert.
 */
function showAlertItemInfoWindow(alertItem) {
  var title = alertItem.cap.info.headline.$t;

  var snippetHtml = tmpl('tpl_alert_bubble_small', alertItem.cap);
  var fullHtml = tmpl('tpl_alert_bubble_large', alertItem.cap);

  for (var overlayIdx in alertItem.overlays) {
    var overlay = alertItem.overlays[overlayIdx];
    overlay.openInfoWindowHtml(snippetHtml, {
        maxContent: fullHtml,
        maxTitle: title,
        maxWidth: 400
        });
  }
}
