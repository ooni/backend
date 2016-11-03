import del from "del";
import gulp from "gulp";
import path from "path";
import gulpBatch from "gulp-batch";
import gulpSass from "gulp-sass";
import gulpSequence  from "gulp-sequence";
import gulpSourcemaps from "gulp-sourcemaps";
import gulpWatch from "gulp-watch";
import gutil from "gulp-util";
import named from "vinyl-named";
import webpack from "webpack";
import webpackStream from "webpack-stream";

import ExtractTextPlugin from "extract-text-webpack-plugin";
let ProvidePlugin = webpack.ProvidePlugin;
let DedupePlugin = webpack.optimize.DedupePlugin;

let basePrefix = __dirname;
let staticPrefix = path.join(basePrefix, "measurements", "static");
let distPath = path.join(staticPrefix, "dist");
let publicPath = "/static/";
let modulesPath = path.join(basePrefix, "node_modules");

let webpackConfig = {
  quiet: false,
  verbose: true,
  stats: {
    colors: true,
    modules: true,
    reasons: true,
    errorDetails: true
  },
  output: {
    //publicPath: path.join(publicPath, "scripts"),
    filename: "[name].js",
    chunkFilename: "chunks/[chunkhash].js"
  },
  module: {
    loaders: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        loader: "babel",
        query: { presets: ["es2015"]}
      },
      {
        test: /\.(ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/,
        loader: 'file-loader',
      },
      {
        test: /\.scss$/,
        loader: ExtractTextPlugin.extract('style-loader', 'css!sass?includePaths[]=' + basePrefix)
      }
    ]
  },
  plugins: [
    new ProvidePlugin({
      $: 'jquery',
      jQuery: 'jquery',
      d3: 'd3'
    }),
    new DedupePlugin(),
    new ExtractTextPlugin('[name].css')
  ],
  resolve: {
    extensions: ["", ".js", ".scss"]
  }
};


gulp.task("dist:js", () => {

  let files = [
    path.resolve(staticPrefix, 'scripts', 'main.js'),
    path.resolve(staticPrefix, 'scripts', 'stats.js'),
    path.resolve(staticPrefix, 'scripts', 'country_flag.js')
  ];

  return gulp.src(files)
    .pipe(named())
    .pipe(webpackStream(webpackConfig, webpack))
    .pipe(gulpSourcemaps.init({ loadMaps: true }))
    .pipe(gulpSourcemaps.write("."))
    .pipe(gulp.dest(path.join(distPath, "js")));
});

gulp.task('dist:icons:font-awesome', () => {
  let faPath = path.dirname(require.resolve("font-awesome/package.json"));
  let faFontPath = path.resolve(faPath, "fonts", "*.*");
  
  return gulp.src(faFontPath)
            .pipe(gulp.dest(path.join(distPath, "fonts"))); 
});

gulp.task('dist:icons:bootstrap', () => { 
  let bootstrapPath = path.dirname(require.resolve("bootstrap-sass/package.json"));
  let bootstrapFontPath = path.resolve(bootstrapPath, "assets", "fonts", "**", "*");
  
  return gulp.src(bootstrapFontPath)
            .pipe(gulp.dest(path.join(distPath, "fonts")));  
});

gulp.task('dist:icons', ['dist:icons:font-awesome', 'dist:icons:bootstrap']);

gulp.task('dist:flags', () => {
  let flagPath = path.dirname(require.resolve("flag-icon-css/package.json"));
  let flagSvgPath = path.resolve(flagPath, "flags", "**", "*");

  return gulp.src(flagSvgPath)
    .pipe(gulp.dest(path.join(distPath, "flags")));
});

gulp.task("dist:css", () => {
  let stylesPath = path.join(staticPrefix, "styles");
  let files = [
    path.join(stylesPath, "by_date.scss"),
    path.join(stylesPath, "main.scss"),
    path.join(stylesPath, "stats.scss"),
    path.join(stylesPath, "country_flag.scss"),
    path.join(modulesPath, "metrics-graphics", "dist", "metricsgraphics.css")
  ];

  return gulp.src(files)
    .pipe(gulpSourcemaps.init())
    .pipe(
      gulpSass({
        includePaths: [
          stylesPath,
          modulesPath
        ]
      }).on("error", gulpSass.logError)
    )
    .pipe(gulpSourcemaps.write("."))
    .pipe(gulp.dest(path.join(distPath, "css")));
});

gulp.task("dist", (cb) => {
  return gulpSequence(
    "clean",
    "dist:icons",
    "dist:flags",
    ["dist:css", "dist:js"]
  )(cb);
});

gulp.task("watch", ["dist"], () => {
  let watchPaths = [
    path.join(staticPrefix, "**", "*"),
    path.join("!" + distPath, "**", "*"),
  ];

  gulpWatch(
    watchPaths,
    gulpBatch((_, done) => { gulp.start("dist", done); })
  );
});

gulp.task("clean", () => { del(distPath); });

gulp.task("watch", () => )
