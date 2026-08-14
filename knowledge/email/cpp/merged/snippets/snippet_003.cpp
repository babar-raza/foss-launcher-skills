int main(int argc, char* argv[])
{
    if (argc < 2)
    {
        std::cerr << "Usage: msg_summary.cpp <path-to-msg> [--body-preview-chars <count>] [--property-id <id>] [--property-type <type>]\n";
        return 1;
    }

    const std::filesystem::path msg_path(argv[1]);
    const auto body_limit_text = read_option(argc, argv, "--body-preview-chars");
    const auto property_id_text = read_option(argc, argv, "--property-id");
    const auto property_type_text = read_option(argc, argv, "--property-type");
    const auto body_limit = body_limit_text.empty() ? 400U : static_cast<std::size_t>(std::stoul(body_limit_text));

    const auto message = aspose::email::foss::msg::mapi_message::from_file(msg_path);

    std::cout << "Message Summary:\n";
    std::cout << "file: " << msg_path.string() << '\n';
    std::cout << "subject: " << message.subject() << '\n';
    std::cout << "message_class: " << message.message_class() << '\n';
    std::cout << "sender_name: " << message.sender_name() << '\n';
    std::cout << "sender_email: " << message.sender_email_address() << '\n';
    std::cout << "internet_message_id: " << message.internet_message_id() << '\n';
    std::cout << "recipients_count: " << message.recipients().size() << '\n';
    std::cout << "attachments_count: " << message.attachments().size() << '\n';
    std::cout << "validation_issues: " << message.validation_issues().size() << '\n';

    std::cout << "\nDisplay Recipients:\n";
    std::cout << "- To: " << any_string(message.get_property_value(
        to_underlying(aspose::email::foss::msg::common_message_property_id::display_to),
        to_underlying(aspose::email::foss::msg::property_type_code::ptyp_string))) << '\n';
    std::cout << "- Cc: " << any_string(message.get_property_value(
        to_underlying(aspose::email::foss::msg::common_message_property_id::display_cc),
        to_underlying(aspose::email::foss::msg::property_type_code::ptyp_string))) << '\n';
    std::cout << "- Bcc: " << any_string(message.get_property_value(
        to_underlying(aspose::email::foss::msg::common_message_property_id::display_bcc),
        to_underlying(aspose::email::foss::msg::property_type_code::ptyp_string))) << '\n';

    print_transport_headers(message);

    std::cout << "\nRecipients:\n";
    if (message.recipients().empty())
    {
        std::cout << "- <none>\n";
    }
    else
    {
        for (std::size_t index = 0; index < message.recipients().size(); ++index)
        {
            const auto& recipient = message.recipients()[index];
            std::cout
                << "- [" << (index + 1U) << "] name=" << recipient.display_name
                << " email=" << recipient.email_address
                << " type=" << recipient.recipient_type
                << '\n';
        }
    }

    std::cout << "\nBody Preview:\n";
    const auto& body = message.html_body().empty() ? message.body() : message.html_body();
    const auto preview = body_preview(body, body_limit);
    std::cout << preview << '\n';
    if (body.size() > preview.size())
    {
        std::cout << "... (" << (body.size() - preview.size()) << " more chars omitted)\n";
    }

    std::cout << "\nAttachments:\n";
    if (message.attachments().empty())
    {
        std::cout << "- <none>\n";
    }
    else
    {
        for (std::size_t index = 0; index < message.attachments().size(); ++index)
        {
            const auto& attachment = message.attachments()[index];
            std::cout
                << "- [" << (index + 1U) << "] name=" << attachment.filename
                << " mime=" << attachment.mime_type
                << " size=" << attachment.data.size()
                << " content_id=" << attachment.content_id
                << " embedded=" << (attachment.is_embedded_message() ? "true" : "false")
                << '\n';
        }
    }

    std::cout << "\nAttachment Memory Read Check:\n";
    if (message.attachments().empty())
    {
        std::cout << "- <none>\n";
    }
    else
    {
        for (std::size_t index = 0; index < message.attachments().size(); ++index)
        {
            const auto& attachment = message.attachments()[index];
            const auto bytes_in_memory = attachment.is_embedded_message() && attachment.embedded_message != nullptr
                ? attachment.embedded_message->save().size()
                : attachment.data.size();
            std::cout
                << "- [" << (index + 1U) << "] name=" << attachment.filename
                << " read_ok=true bytes_in_memory=" << bytes_in_memory
                << " content_type=" << attachment.mime_type
                << '\n';
        }
    }

    if (!property_id_text.empty())
    {
        const auto property_id = parse_u16(property_id_text);
        const auto property_type = property_type_text.empty()
            ? std::optional<std::uint16_t> {}
            : std: