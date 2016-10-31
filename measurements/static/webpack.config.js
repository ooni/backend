var webpack = require('webpack');
var path = require('path');
var fs = require('fs');

var CommonsChunkPlugin = webpack.optimize.CommonsChunkPlugin;
var ExtractTextPlugin = require("extract-text-webpack-plugin");
var ProvidePlugin = webpack.ProvidePlugin;

// input dir
var APP_DIR = path.resolve(__dirname, './');

// output dir
var BUILD_DIR = path.resolve(__dirname, './dist');

var config = {
  entry: {
    main: path.resolve(APP_DIR, 'scripts', 'main.js'),
    stats: path.resolve(APP_DIR, 'scripts', 'stats.js'),
    country_flag: path.resolve(APP_DIR, 'scripts', 'country_flag.js'),
    vendor: ["jquery", "jquery-ui", "bootstrap", "d3", "metrics-graphics"]
  },
  output: {
    path: BUILD_DIR,
    filename: "[name].js"
  },
  module: {
    loaders: [
      /* for font-awesome */
      {
        test: /\.woff(2)?(\?v=[0-9]\.[0-9]\.[0-9])?$/,
        loader: 'url-loader?limit=10000&minetype=application/font-woff',
      },
      {
        test: /\.(ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/,
        loader: 'file-loader',
      },
      {
        test: /\.scss$/,
        loader: ExtractTextPlugin.extract('style-loader', 'css!sass?includePaths[]=' + APP_DIR)
      }
    ]
  },
  plugins: [
    new ProvidePlugin({
      $: 'jquery',
      jQuery: 'jquery'
    }),
    new CommonsChunkPlugin("vendor", "vendor.main.js"),
    new ExtractTextPlugin('[name].css')
  ],
  resolve: {
    extensions: ['', '.js', '.scss'],
    root: [APP_DIR]
  }
};
module.exports = config;
