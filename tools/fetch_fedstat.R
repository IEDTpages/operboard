#!/usr/bin/env Rscript

# Network bridge for Operboard. All Fedstat requests and SDMX parsing are
# performed by fedstatAPIr; Python receives only JSON tables.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: fetch_fedstat.R ids INDICATOR OUTPUT | data INDICATOR INPUT OUTPUT")
}

suppressPackageStartupMessages({
  library(fedstatAPIr)
  library(httr)
  library(jsonlite)
})

mode <- args[[1]]
indicator_id <- args[[2]]
output_path <- args[[length(args)]]
user_agent <- Sys.getenv(
  "FEDSTAT_USER_AGENT",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
timeout_seconds <- as.numeric(Sys.getenv("FEDSTAT_TIMEOUT_SECONDS", "90"))
retry_max <- as.integer(Sys.getenv("FEDSTAT_RETRY_MAX", "3"))
request_headers <- httr::add_headers(
  .headers = c(
    "user-agent" = user_agent,
    "accept-language" = "ru-RU,ru;q=0.9,en;q=0.8",
    "accept" = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
  )
)

if (mode == "ids") {
  result <- fedstatAPIr::fedstat_get_data_ids(
    indicator_id,
    request_headers,
    timeout_seconds = timeout_seconds,
    retry_max_times = retry_max
  )
  jsonlite::write_json(
    result,
    output_path,
    dataframe = "rows",
    auto_unbox = TRUE,
    na = "null",
    pretty = FALSE
  )
} else if (mode == "data") {
  if (length(args) != 4) {
    stop("data mode expects INDICATOR INPUT OUTPUT")
  }
  selected_ids <- jsonlite::read_json(args[[3]], simplifyVector = TRUE)
  selected_ids <- as.data.frame(selected_ids, stringsAsFactors = FALSE)
  expected <- c(
    "filter_field_id", "filter_field_title", "filter_value_id",
    "filter_value_title", "filter_field_object_ids"
  )
  missing <- setdiff(expected, names(selected_ids))
  if (length(missing)) {
    stop(paste("Missing selected-id columns:", paste(missing, collapse = ", ")))
  }
  selected_ids[expected] <- lapply(selected_ids[expected], as.character)
  raw_sdmx <- fedstatAPIr::fedstat_post_data_ids_filtered(
    selected_ids,
    request_headers,
    data_format = "sdmx",
    timeout_seconds = timeout_seconds,
    retry_max_times = retry_max
  )
  result <- fedstatAPIr::fedstat_parse_sdmx_to_table(raw_sdmx)
  jsonlite::write_json(
    as.data.frame(result),
    output_path,
    dataframe = "rows",
    auto_unbox = TRUE,
    na = "null",
    digits = NA,
    pretty = FALSE
  )
} else {
  stop(paste("Unknown mode:", mode))
}
