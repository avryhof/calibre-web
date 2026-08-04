/* Physical book collection: ISBN metadata lookup (modal) + barcode scanning.
 * Depends on jQuery + underscore (main.js provides getPath() + global CSRF header for POSTs).
 */
/* global _, Html5Qrcode, Html5QrcodeSupportedFormats, getPath, physicalI18n, tinymce */

$(function () {
    var msg = physicalI18n;

    var language = document.documentElement.lang || "en";
    if ($("#notes").length && typeof tinymce !== "undefined") {
        tinymce.init({
            selector: "#notes",
            plugins: "code",
            branding: false,
            menubar: "edit view format",
            language: language
        });
    }
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

    var templates = {
        bookResult: _.template($("#template-book-result").html())
    };

    function getUniqueValues(inputId, values) {
        var presentArray = $.map($("#" + inputId).val().split(","), $.trim);
        if (presentArray.length === 1 && presentArray[0] === "") {
            presentArray = [];
        }
        $.each(values || [], function (i, el) {
            if ($.inArray(el, presentArray) === -1) presentArray.push(el);
        });
        return presentArray;
    }

    function populateIdentifiers(identifiers) {
        for (var prop in identifiers) {
            if (!identifiers.hasOwnProperty(prop)) continue;
            if ($('input[name="identifier-type-' + prop + '"]').length) {
                $('input[name="identifier-val-' + prop + '"]').val(identifiers[prop]);
            } else {
                addIdentifier(prop, identifiers[prop]);
            }
        }
    }

    function addIdentifier(name, value) {
        var rand_id = Math.floor(Math.random() * 1000000).toString();
        var line = '<tr>';
        line += '<td><input type="text" class="form-control" name="identifier-type-' + rand_id +
            '" required="required" list="identifier-types" value="' + name + '" aria-label="' + msg.identifier_type +
            '" placeholder="' + msg.identifier_type + '"></td>';
        line += '<td><input type="text" class="form-control" name="identifier-val-' + rand_id +
            '" required="required" value="' + value + '" aria-label="' + msg.identifier_value +
            '" placeholder="' + msg.identifier_value + '"></td>';
        line += '<td><button type="button" class="btn btn-default" onclick="removeIdentifierLine(this)">' +
            msg.remove + '</button></td>';
        line += '</tr>';
        $("#identifier-table").append(line);
    }

    function populateForm(book) {
        $title.val(book.title || "");
        $authors.val((book.authors || []).join(" & "));
        $publisher.val(book.publisher || "");
        $publishedDate.val(book.publishedDate || "");
        if (book.tags) {
            var uniqueTags = getUniqueValues('categories', book.tags);
            $("#categories").val(uniqueTags.join(", "));
        }
        if (typeof book.series !== "undefined" && book.series) {
            $("#series").val(book.series);
            $("#series_index").val(book.series_index || 0);
        }
        if (typeof book.description !== "undefined") {
            var editor = tinymce ? tinymce.get("notes") : null;
            if (editor) {
                editor.setContent(book.description || "");
            } else {
                $("#notes").val(book.description || "");
            }
        }
        if (book.rating) {
            $("#rating").data("rating").setValue(Math.round(book.rating));
        }
        if (book.identifiers) {
            populateIdentifiers(book.identifiers);
            if (book.identifiers.isbn) {
                $isbn.val(book.identifiers.isbn);
            }
        }
        if (book.cover) {
            $coverUrl.val(book.cover);
            $("#cover-preview img").attr("src", book.cover);
        }
    }

    function doSearch(keyword) {
        if (!keyword) {
            return;
        }
        $metaInfo.text(msg.loading);
        $.ajax({
            url: getPath() + "/metadata/search",
            type: "POST",
            data: {"query": keyword},
            dataType: "json",
            success: function (data) {
                if (data.length) {
                    $metaInfo.html('<ul id="book-list" class="media-list"></ul>');
                    data.forEach(function (book) {
                        var $book = $(templates.bookResult(book));
                        $book.find("img").on("click", function () {
                            populateForm(book);
                            $("#metaModal").modal("hide");
                        });
                        $("#book-list").append($book);
                    });
                } else {
                    $metaInfo.html('<p class="text-danger">' + msg.no_result + "</p>");
                }
            },
            error: function () {
                $metaInfo.html('<p class="text-danger">' + msg.search_error + "</p>");
            }
        });
    }

    function populate_provider() {
        $("#metadata_provider").empty();
        $.ajax({
            url: getPath() + "/metadata/provider",
            type: "get",
            dataType: "json",
            success: function (data) {
                data.forEach(function (provider) {
                    var checked = provider.active ? "checked" : "";
                    var $provider_button =
                        '<input type="checkbox" id="show-' + provider.name + '" class="pill" data-initial="' +
                        provider.initial + '" data-control="' + provider.id + '" ' + checked + '>' +
                        '<label for="show-' + provider.name + '">' + provider.name +
                        ' <span class="glyphicon glyphicon-ok"></span></label>';
                    $("#metadata_provider").append($provider_button);
                });
            }
        });
    }

    function openModal(keyword) {
        populate_provider();
        $("#keyword").val(keyword);
        $("#meta-info").empty();
        doSearch(keyword);
        $("#metaModal").modal("show");
    }

    $(document).on("change", ".pill", function () {
        var element = $(this);
        var id = element.data("control");
        var initial = element.data("initial");
        var val = element.prop('checked');
        var params = {id: id, value: val};
        if (!initial) {
            params['initial'] = initial;
            params['query'] = $("#keyword").val();
        }
        $.ajax({
            method: "post",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            url: getPath() + "/metadata/provider/" + id,
            data: JSON.stringify(params),
            success: function (data) {
                element.data("initial", "true");
                data.forEach(function (book) {
                    var $book = $(templates.bookResult(book));
                    $book.find("img").on("click", function () {
                        populateForm(book);
                        $("#metaModal").modal("hide");
                    });
                    $("#book-list").append($book);
                });
            }
        });
    });

    $("#meta-search").on("submit", function (e) {
        e.preventDefault();
        $('.pill').each(function () {
            $(this).data("initial", $(this).prop('checked'));
        });
        doSearch($("#keyword").val());
    });

    $("#get_meta").click(function (e) {
        e.preventDefault();
        openModal($isbn.val().trim() || $title.val().trim());
    });

    $("#lookup-isbn").click(function () {
        var isbn = $isbn.val().trim();
        if (!isbn) {
            $isbn.focus();
            return;
        }
        openModal(isbn);
    });

    $("#isbn").on("keypress", function (e) {
        if (e.which === 13) {
            e.preventDefault();
            var isbn = $isbn.val().trim();
            if (isbn) {
                openModal(isbn);
            }
        }
    });

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
                openModal(decodedText);
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
