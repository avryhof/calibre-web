/* Physical book collection: ISBN metadata lookup + barcode scanning.
 * Depends on jQuery (main.js provides getPath() + global CSRF header for POSTs).
 */
/* global Html5Qrcode, Html5QrcodeSupportedFormats, getPath, physicalI18n */

$(function () {
    var msg = physicalI18n;
    var $isbn = $("#isbn");
    var $title = $("#title");
    var $authors = $("#authors");
    var $publisher = $("#publisher");
    var $publishedDate = $("#published_date");
    var $coverUrl = $("#cover_url");
    var $metaInfo = $("#meta-info");
    var $reader = $("#reader");
    var $scanButton = $("#scan-barcode");
    var scanner = null;
    var scanning = false;

    var SUPPORTED_FORMATS = [
        Html5QrcodeSupportedFormats.EAN_13,
        Html5QrcodeSupportedFormats.EAN_8,
        Html5QrcodeSupportedFormats.CODE_128,
        Html5QrcodeSupportedFormats.CODE_39,
        Html5QrcodeSupportedFormats.QR_CODE
    ];

    function showMetaResults(data) {
        if (!data.length) {
            $metaInfo.html('<p class="text-danger">' + msg.no_result + "</p>");
            return;
        }
        var html = '<ul class="media-list physical-meta-results">';
        data.forEach(function (book) {
            html += '<li class="media physical-meta-result">';
            html += '<img class="pull-left img-responsive physical-meta-cover" src="' +
                (book.cover ? book.cover : getPath() + "/static/img/academicpaper.svg") +
                '" alt="Cover">';
            html += '<div class="media-body">';
            html += '<h4 class="media-heading">' + (book.title || "") + "</h4>";
            html += '<p class="meta_author">' + ((book.authors || []).join(" & ")) + "</p>";
            if (book.publisher) {
                html += '<p class="meta_publisher">' + book.publisher + "</p>";
            }
            html += "</div></li>";
        });
        html += "</ul>";
        var $results = $(html);
        $results.find(".physical-meta-result").each(function (index) {
            $(this).data("book", data[index]);
        });
        $metaInfo.html($results);
    }

    function populateForm(book) {
        $title.val(book.title || "");
        $authors.val((book.authors || []).join(" & "));
        $publisher.val(book.publisher || "");
        $publishedDate.val(book.publishedDate || "");
        if (book.cover) {
            $coverUrl.val(book.cover);
            $("#cover-preview img").attr("src", book.cover);
        }
        if (book.identifiers && book.identifiers.isbn) {
            $isbn.val(book.identifiers.isbn);
        }
        if (typeof book.series !== "undefined") {
            $("#series").val(book.series);
            $("#series_index").val(book.series_index);
        }
    }

    function lookupIsbn() {
        var isbn = $isbn.val().trim();
        if (!isbn) {
            return;
        }
        $metaInfo.html('<p class="text-muted">' + msg.loading + "</p>");
        $.ajax({
            url: getPath() + "/metadata/search",
            type: "POST",
            data: {"query": isbn},
            dataType: "json",
            success: function (data) {
                showMetaResults(data);
            },
            error: function () {
                $metaInfo.html('<p class="text-danger">' + msg.search_error + "</p>");
            }
        });
    }

    function stopScanner() {
        if (!scanner) {
            return;
        }
        var current = scanner;
        scanner = null;
        scanning = false;
        current.stop().then(function () {
            current.clear();
            $reader.hide();
        }).catch(function () {
            $reader.hide();
        });
        $scanButton.html('<span class="glyphicon glyphicon-camera"></span> ' +
            $scanButton.data("scan-label"));
    }

    function startScanner() {
        $scanButton.data("scan-label", $scanButton.text().trim());
        $reader.show();
        $scanButton.text(msg.stop_scan);
        try {
            scanner = new Html5Qrcode("reader");
        } catch (e) {
            $reader.hide();
            scanning = false;
            $scanButton.html('<span class="glyphicon glyphicon-camera"></span> ' +
                $scanButton.data("scan-label"));
            alert(msg.scan_error);
            return;
        }
        scanner.start(
            {facingMode: "environment"},
            {fps: 10, qrbox: {width: 250, height: 250}, formatsToSupport: SUPPORTED_FORMATS},
            function (decodedText) {
                $isbn.val(decodedText);
                stopScanner();
                lookupIsbn();
            },
            function () {}
        ).catch(function () {
            scanning = false;
            $reader.hide();
            $scanButton.html('<span class="glyphicon glyphicon-camera"></span> ' +
                $scanButton.data("scan-label"));
            alert(msg.scan_error);
        });
    }

    $(document).on("click", ".physical-meta-result", function () {
        populateForm($(this).data("book"));
        $metaInfo.empty();
    });

    $("#lookup-isbn").click(function () {
        lookupIsbn();
    });

    $("#isbn").on("keypress", function (e) {
        if (e.which === 13) {
            e.preventDefault();
            lookupIsbn();
        }
    });

    $scanButton.click(function () {
        if (scanning) {
            stopScanner();
        } else {
            scanning = true;
            startScanner();
        }
    });

    $("#cover").change(function () {
        if (this.files && this.files[0]) {
            var reader = new FileReader();
            reader.onload = function (e) {
                $("#cover-preview img").attr("src", e.target.result);
            };
            reader.readAsDataURL(this.files[0]);
        }
    });
});
